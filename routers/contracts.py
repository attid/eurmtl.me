from __future__ import annotations

import os
from uuid import uuid4

from loguru import logger
from quart import Blueprint, abort, jsonify, render_template, request, session

from other.config_reader import config, start_path
from other.grist_tools import load_user_from_grist
from other.qr_tools import create_beautiful_code
from other.stellar_soroban import submit_signed_transaction
from other.web_tools import http_session_manager
from services.contracts.flow_service import ContractsFlowService
from services.contracts.handlers.mountain_contract import (
    choose_candidate_address,
    load_message,
    prepare_capture_flow as prepare_mountain_capture_flow,
    validate_capture_form,
)
from services.contracts.handlers.swap_pool_contract import (
    SWAP_POOL_CONTRACT_ID,
    estimate_swap_exact_in,
    estimate_swap_exact_out,
    load_pool_overview as load_swap_pool_overview,
    prepare_swap_exact_in_flow,
    prepare_swap_exact_out_flow,
    validate_swap_exact_in_form,
    validate_swap_exact_out_form,
)
from services.contracts.registry import get_contract, list_public_contracts
from services.xdr_parser import is_valid_base64

blueprint = Blueprint("contracts", __name__)


def _resolve_swap_direction(direction: str) -> tuple[str, str]:
    normalized = direction.strip().upper()
    if normalized == "EURMTL_TO_USDM":
        return "EURMTL", "USDM"
    if normalized == "USDM_TO_EURMTL":
        return "USDM", "EURMTL"
    raise ValueError("Invalid swap direction")


async def prepare_capture_flow(contract_id: str, form_data: dict) -> dict:
    marker = _get_contracts_session_marker()
    flow_service = ContractsFlowService()
    flow = flow_service.create_flow(
        session_marker=marker,
        contract_id=contract_id,
        action_name="capture",
        form_data=form_data,
    )
    callback_url = f"https://{config.domain}/contracts/callback/{flow['request_id']}"
    prepared = await prepare_mountain_capture_flow(
        contract_id=contract_id,
        user=form_data["user"],
        amount=form_data["amount"],
        msg=form_data["msg"],
        callback_url=callback_url,
    )
    qr_url = f"/static/qr/contracts-{flow['request_id']}.png"
    os.makedirs(os.path.join(start_path, "static", "qr"), exist_ok=True)
    qr_error = ""
    try:
        create_beautiful_code(qr_url, "Capture", prepared["uri"])
    except ValueError:
        qr_url = ""
        qr_error = "URI too long for QR generation"
    flow_service.update_flow_prepare_data(
        flow["request_id"],
        unsigned_xdr=prepared["xdr"],
        uri=prepared["uri"],
        qr_url=qr_url,
    )
    return {
        "request_id": flow["request_id"],
        "uri": prepared["uri"],
        "qr_url": qr_url,
        "qr_error": qr_error,
    }


async def prepare_swap_flow(action_name: str, form_data: dict) -> dict:
    marker = _get_contracts_session_marker()
    flow_service = ContractsFlowService()
    flow = flow_service.create_flow(
        session_marker=marker,
        contract_id=SWAP_POOL_CONTRACT_ID,
        action_name=action_name,
        form_data=form_data,
    )
    callback_url = f"https://{config.domain}/contracts/callback/{flow['request_id']}"
    if action_name == "swap":
        prepared = await prepare_swap_exact_in_flow(
            user=form_data["user"],
            from_token=form_data["from_token"],
            to_token=form_data["to_token"],
            amount_in=form_data["amount_in"],
            callback_url=callback_url,
            slippage_percent=form_data.get("slippage_percent", "1"),
        )
        qr_title = "Swap"
    else:
        prepared = await prepare_swap_exact_out_flow(
            user=form_data["user"],
            from_token=form_data["from_token"],
            to_token=form_data["to_token"],
            amount_out=form_data["amount_out"],
            callback_url=callback_url,
            slippage_percent=form_data.get("slippage_percent", "1"),
        )
        qr_title = "Swap exact out"
    qr_url = f"/static/qr/contracts-{flow['request_id']}.png"
    os.makedirs(os.path.join(start_path, "static", "qr"), exist_ok=True)
    qr_error = ""
    try:
        create_beautiful_code(qr_url, qr_title, prepared["uri"])
    except ValueError:
        qr_url = ""
        qr_error = "URI too long for QR generation"
    flow_service.update_flow_prepare_data(
        flow["request_id"],
        unsigned_xdr=prepared["xdr"],
        uri=prepared["uri"],
        qr_url=qr_url,
    )
    return {
        "request_id": flow["request_id"],
        "uri": prepared["uri"],
        "qr_url": qr_url,
        "qr_error": qr_error,
    }


def _get_contracts_session_marker() -> str:
    marker = session.get("contracts_session_marker")
    if marker:
        return marker
    marker = uuid4().hex
    session["contracts_session_marker"] = marker
    return marker


async def _get_detected_user_address() -> str:
    telegram_id = session.get("userdata", {}).get("id")
    if not telegram_id:
        return ""

    try:
        user = await load_user_from_grist(telegram_id=int(telegram_id))
    except Exception:
        return ""

    return user.account_id if user and user.account_id else ""


@blueprint.route("/contracts")
@blueprint.route("/contracts/")
async def contracts_index():
    return await render_template(
        "contracts_list.html",
        contracts=list_public_contracts(),
    )


@blueprint.route("/contracts/<contract_id>")
async def contract_detail(contract_id: str):
    contract = get_contract(contract_id)
    if contract is None:
        abort(404)

    message_result = {"ok": False, "message": "", "error": ""}
    pool_overview = None
    if contract_id == "CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM":
        message_result = await load_message(contract_id)
    if contract_id == SWAP_POOL_CONTRACT_ID:
        pool_overview = await load_swap_pool_overview()

    detected_user_address = await _get_detected_user_address()
    prefill_user = choose_candidate_address(
        detected_address=detected_user_address,
        session_address=session.get("contracts_last_used_address", ""),
    )

    return await render_template(
        "contract_detail.html",
        contract=contract,
        message_result=message_result,
        pool_overview=pool_overview,
        prefill_user=prefill_user,
        detected_user_address=detected_user_address,
    )


@blueprint.route("/contracts/<contract_id>/actions/message")
async def contract_message_action(contract_id: str):
    contract = get_contract(contract_id)
    if contract is None:
        abort(404)

    return jsonify(await load_message(contract_id))


@blueprint.route("/contracts/<contract_id>/actions/estimate-swap", methods=["POST"])
async def contract_estimate_swap(contract_id: str):
    if contract_id != SWAP_POOL_CONTRACT_ID:
        abort(404)
    form = await request.form
    try:
        from_token, to_token = _resolve_swap_direction(form.get("direction") or "")
    except ValueError:
        from_token = (form.get("from_token") or "").strip()
        to_token = (form.get("to_token") or "").strip()
    return jsonify(
        await estimate_swap_exact_in(
            from_token=from_token,
            to_token=to_token,
            amount_in=(form.get("amount_in") or "").strip(),
        )
    )


@blueprint.route(
    "/contracts/<contract_id>/actions/estimate-swap-strict-receive", methods=["POST"]
)
async def contract_estimate_swap_strict_receive(contract_id: str):
    if contract_id != SWAP_POOL_CONTRACT_ID:
        abort(404)
    form = await request.form
    try:
        from_token, to_token = _resolve_swap_direction(form.get("direction") or "")
    except ValueError:
        from_token = (form.get("from_token") or "").strip()
        to_token = (form.get("to_token") or "").strip()
    return jsonify(
        await estimate_swap_exact_out(
            from_token=from_token,
            to_token=to_token,
            amount_out=(form.get("amount_out") or "").strip(),
        )
    )


@blueprint.route("/contracts/<contract_id>/actions/swap/prepare", methods=["POST"])
async def contract_swap_prepare(contract_id: str):
    if contract_id != SWAP_POOL_CONTRACT_ID:
        abort(404)

    form = await request.form
    try:
        from_token, to_token = _resolve_swap_direction(form.get("direction") or "")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    user = (form.get("user") or "").strip()
    amount_in = (form.get("amount_in") or "").strip()
    slippage_percent = (form.get("slippage") or "1").strip()
    error = validate_swap_exact_in_form(user, amount_in, slippage_percent)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    session["contracts_last_used_address"] = user
    _get_contracts_session_marker()

    try:
        result = await prepare_swap_flow(
            "swap",
            {
                "user": user,
                "from_token": from_token,
                "to_token": to_token,
                "amount_in": amount_in,
                "slippage_percent": slippage_percent,
                "direction": (form.get("direction") or "").strip(),
            },
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "qr_error": "", **result})


@blueprint.route(
    "/contracts/<contract_id>/actions/swap-strict-receive/prepare", methods=["POST"]
)
async def contract_swap_strict_receive_prepare(contract_id: str):
    if contract_id != SWAP_POOL_CONTRACT_ID:
        abort(404)

    form = await request.form
    try:
        from_token, to_token = _resolve_swap_direction(form.get("direction") or "")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    user = (form.get("user") or "").strip()
    amount_out = (form.get("amount_out") or "").strip()
    slippage_percent = (form.get("slippage") or "1").strip()
    error = validate_swap_exact_out_form(user, amount_out, slippage_percent)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    session["contracts_last_used_address"] = user
    _get_contracts_session_marker()

    try:
        result = await prepare_swap_flow(
            "swap_strict_receive",
            {
                "user": user,
                "from_token": from_token,
                "to_token": to_token,
                "amount_out": amount_out,
                "slippage_percent": slippage_percent,
                "direction": (form.get("direction") or "").strip(),
            },
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "qr_error": "", **result})


@blueprint.route("/contracts/<contract_id>/actions/capture/prepare", methods=["POST"])
async def contract_capture_prepare(contract_id: str):
    contract = get_contract(contract_id)
    if contract is None:
        abort(404)

    form = await request.form
    user = (form.get("user") or "").strip()
    amount = (form.get("amount") or "").strip()
    msg = (form.get("msg") or "").strip()

    error = validate_capture_form(user, amount, msg)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    session["contracts_last_used_address"] = user
    _get_contracts_session_marker()

    try:
        result = await prepare_capture_flow(
            contract_id,
            {"user": user, "amount": amount, "msg": msg},
        )
    except Exception as exc:
        logger.exception(
            "contracts capture prepare failed: contract_id={} user={} amount={} msg={} error={}",
            contract_id,
            user,
            amount,
            msg,
            str(exc),
        )
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "qr_error": "", **result})


@blueprint.route("/contracts/flow/<request_id>/status")
async def contracts_flow_status(request_id: str):
    marker = _get_contracts_session_marker()
    flow = ContractsFlowService().get_flow(request_id, session_marker=marker)
    if flow is None:
        return jsonify({"ok": False, "error": "Flow not found"}), 404
    return jsonify({"ok": True, "flow": flow})


@blueprint.route("/contracts/send", methods=["GET", "POST"])
async def contracts_send_page():
    form_xdr = ""
    submit_result = None

    if request.method == "POST":
        form = await request.form
        form_xdr = (form.get("signed_xdr") or "").strip()
        if not form_xdr or not is_valid_base64(form_xdr):
            submit_result = {
                "ok": False,
                "tx_hash": "",
                "error": "Invalid or missing base64 data",
            }
        else:
            logger.info(
                "contracts send page submit requested: xdr_length={}",
                len(form_xdr),
            )
            submit_result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr=form_xdr,
            )
            logger.info(
                "contracts send page submit result: ok={} tx_hash={} error={}",
                submit_result["ok"],
                submit_result["tx_hash"],
                submit_result["error"],
            )

    return await render_template(
        "contracts_send.html",
        signed_xdr=form_xdr,
        submit_result=submit_result,
    )


@blueprint.route("/contracts/flow/<request_id>/mmwb", methods=["POST"])
async def contracts_flow_mmwb(request_id: str):
    marker = _get_contracts_session_marker()
    flow = ContractsFlowService().get_flow(request_id, session_marker=marker)
    if flow is None:
        return jsonify({"ok": False, "error": "Flow not found"}), 404
    if not flow.get("uri"):
        return jsonify({"ok": False, "error": "Flow has no prepared URI"}), 400

    response = await http_session_manager.get_web_request(
        "POST",
        f"https://{config.domain}/remote/sep07/add",
        json={"uri": flow["uri"]},
        return_type="json",
    )
    if response.status != 200 or not response.data.get("SUCCESS"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": response.data.get(
                        "message", "Failed to generate MMWB link"
                    ),
                }
            ),
            400,
        )

    return jsonify({"ok": True, "url": response.data["url"]})


@blueprint.route("/contracts/callback/<request_id>", methods=["POST"])
async def contracts_callback(request_id: str):
    form = await request.form
    signed_xdr = form.get("xdr") or ""
    if not signed_xdr or not is_valid_base64(signed_xdr):
        return jsonify({"ok": False, "error": "Invalid or missing base64 data"}), 400

    flow_service = ContractsFlowService()
    flow = flow_service.get_flow_for_callback(request_id)
    if flow is None:
        return jsonify({"ok": False, "error": "Flow not found"}), 404

    submit_result = await submit_signed_transaction(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        signed_xdr=signed_xdr,
    )
    if submit_result["ok"]:
        flow_service.update_flow_result(
            request_id,
            status="submitted",
            tx_hash=submit_result["tx_hash"],
            error_message="",
            signed_xdr=signed_xdr,
        )
        return jsonify(
            {
                "ok": True,
                "status": "submitted",
                "tx_hash": submit_result["tx_hash"],
            }
        )

    flow_service.update_flow_result(
        request_id,
        status="failed",
        tx_hash="",
        error_message=submit_result["error"],
        signed_xdr=signed_xdr,
    )
    return jsonify(
        {
            "ok": False,
            "status": "failed",
            "error": submit_result["error"],
        }
    ), 400
