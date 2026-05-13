from unittest.mock import AsyncMock, patch

import pytest
from stellar_sdk import Keypair

FIRST_CONTRACT_ID = "CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM"
SWAP_CONTRACT_ID = "CCEBV2EC6Z6TE2632XXTEBD6KA2U57LRIEDGV2SU77BOF2HKKB4HDIM2"
HIDDEN_CONTRACT_ID = "CBHIDDENCONTRACTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
VALID_USER = Keypair.random().public_key


@pytest.mark.asyncio
async def test_contracts_index_lists_public_contracts(client):
    response = await client.get("/contracts")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Contracts" in body
    assert "King of the Mountain" in body
    assert "USDM / EURMTL Swap" in body
    assert FIRST_CONTRACT_ID in body
    assert SWAP_CONTRACT_ID in body


@pytest.mark.asyncio
async def test_swap_contract_detail_renders_overview_and_swap_blocks(client):
    with patch(
        "routers.contracts.load_swap_pool_overview",
        new=AsyncMock(
            return_value={
                "contract_name": "StandardLiquidityPool",
                "pool_type": "constant_product",
                "tokens": ["USDM", "EURMTL"],
                "reserves": ["1721.4781021", "1441.5383509"],
                "fee_fraction": 10,
            }
        ),
    ):
        response = await client.get(f"/contracts/{SWAP_CONTRACT_ID}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Pool overview" in body
    assert "Exact in" in body
    assert "Exact out" in body
    assert "USDM" in body
    assert "EURMTL" in body
    assert "EURMTL → USDM" in body
    assert "USDM → EURMTL" in body
    assert 'name="from_token"' not in body
    assert 'name="to_token"' not in body
    assert 'name="direction"' in body
    assert 'name="user"' in body
    assert 'name="slippage"' in body
    assert 'id="exact-in-form"' in body
    assert 'id="exact-out-form"' in body
    assert 'id="exact-in-sep7-button"' in body
    assert 'id="exact-out-sep7-button"' in body
    assert 'id="contractsMmwbGenerateButton"' in body
    assert 'id="contractsMmwbOpenLink"' in body
    assert "valid for 5 minutes" in body


@pytest.mark.asyncio
async def test_mountain_contract_detail_explains_raw_amount_units(client):
    with (
        patch(
            "routers.contracts.load_range",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "min_amount_raw": "10000000",
                    "max_amount_raw": "25000000",
                    "min_amount_eurmtl": "1",
                    "max_amount_eurmtl": "2.5",
                    "error": "",
                }
            ),
        ),
        patch(
            "routers.contracts.notify_mountain_message_change",
            new=AsyncMock(
                return_value={"created": False, "reason": "grist", "error": ""}
            ),
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Amount (in raw units. 1 unit = 0.0000001 EURMTL)" in body
    assert "Amount uses raw token units" in body
    assert "1 EURMTL = 10,000,000 raw units" in body
    assert "1 raw unit = 0.0000001 EURMTL" in body
    assert "Allowed capture range" in body
    assert "10000000" in body
    assert "25000000" in body
    assert "1 EURMTL" in body
    assert "2.5 EURMTL" in body
    assert 'id="message-result"' in body
    assert "white-space: pre-wrap" in body
    assert f'href="https://viewer.eurmtl.me/contract/{FIRST_CONTRACT_ID}"' in body


@pytest.mark.asyncio
async def test_mountain_contract_detail_exposes_current_user_address_without_prefill(
    client,
):
    async with client.session_transaction() as session:
        session["user_id"] = "42"
        session["userdata"] = {"id": "42", "photo_url": "", "username": "tester"}

    with (
        patch(
            "routers.contracts.load_user_from_grist",
            new=AsyncMock(
                return_value=type(
                    "User",
                    (),
                    {"account_id": VALID_USER},
                )()
            ),
        ),
        patch(
            "routers.contracts.load_range",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "min_amount_raw": "10",
                    "max_amount_raw": "20",
                    "min_amount_eurmtl": "0.000001",
                    "max_amount_eurmtl": "0.000002",
                    "error": "",
                }
            ),
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    body = await response.get_data(as_text=True)
    assert 'id="field-user" name="user"' in body
    assert f'const prefillUser = "{VALID_USER}"' in body
    assert f'value="{VALID_USER}"' not in body


@pytest.mark.asyncio
async def test_mountain_contract_detail_notifies_on_page_load_when_message_loaded(
    client,
):
    with (
        patch(
            "routers.contracts.load_message",
            new=AsyncMock(return_value={"ok": True, "message": "Changed", "error": ""}),
        ),
        patch(
            "routers.contracts.load_range",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "min_amount_raw": "1",
                    "max_amount_raw": "2",
                    "min_amount_eurmtl": "0.0000001",
                    "max_amount_eurmtl": "0.0000002",
                    "error": "",
                }
            ),
        ),
        patch(
            "routers.contracts.notify_mountain_message_change",
            new=AsyncMock(
                return_value={"created": True, "reason": "posted", "error": ""}
            ),
        ) as notify_mock,
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    assert response.status_code == 200
    notify_mock.assert_awaited_once_with("Changed")


@pytest.mark.asyncio
async def test_contracts_index_hides_internal_contracts(client):
    response = await client.get("/contracts")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert HIDDEN_CONTRACT_ID not in body
    assert "Hidden test contract" not in body


@pytest.mark.asyncio
async def test_hidden_contract_detail_is_reachable_by_direct_url(client):
    response = await client.get(f"/contracts/{HIDDEN_CONTRACT_ID}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Hidden test contract" in body


@pytest.mark.asyncio
async def test_unknown_contract_returns_404(client):
    response = await client.get("/contracts/UNKNOWN")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_capture_prepare_returns_request_id_uri_and_stores_last_used_address(
    client,
):
    with (
        patch(
            "routers.contracts.load_range",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "min_amount_raw": "10",
                    "max_amount_raw": "20",
                    "min_amount_eurmtl": "0.000001",
                    "max_amount_eurmtl": "0.000002",
                    "error": "",
                }
            ),
        ),
        patch(
            "routers.contracts.prepare_capture_flow",
            new=AsyncMock(
                return_value={
                    "request_id": "req-1",
                    "uri": "web+stellar:tx?xdr=AAAA",
                    "qr_url": "/static/qr/req-1.png",
                }
            ),
        ),
    ):
        response = await client.post(
            f"/contracts/{FIRST_CONTRACT_ID}/actions/capture/prepare",
            form={"user": VALID_USER, "amount": "10", "msg": "For glory"},
        )

    assert response.status_code == 200
    data = await response.get_json()
    assert data == {
        "ok": True,
        "request_id": "req-1",
        "uri": "web+stellar:tx?xdr=AAAA",
        "qr_url": "/static/qr/req-1.png",
        "qr_error": "",
    }

    async with client.session_transaction() as session:
        assert session["contracts_last_used_address"] == VALID_USER


@pytest.mark.asyncio
async def test_capture_prepare_rejects_invalid_payload(client):
    response = await client.post(
        f"/contracts/{FIRST_CONTRACT_ID}/actions/capture/prepare",
        form={"user": "", "amount": "0", "msg": ""},
    )

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "error": "user, amount and msg are required",
    }


@pytest.mark.asyncio
async def test_flow_status_returns_current_state_for_same_session(client):
    async with client.session_transaction() as session:
        session["contracts_session_marker"] = "session-1"

    with patch(
        "routers.contracts.ContractsFlowService.get_flow",
        return_value={
            "request_id": "req-1",
            "status": "submitted",
            "tx_hash": "abc123",
            "error_message": "",
            "signed_xdr": "AAAA",
        },
    ):
        response = await client.get("/contracts/flow/req-1/status")

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "flow": {
            "request_id": "req-1",
            "status": "submitted",
            "tx_hash": "abc123",
            "error_message": "",
            "signed_xdr": "AAAA",
        },
    }


@pytest.mark.asyncio
async def test_flow_status_rejects_request_from_another_session(client):
    async with client.session_transaction() as session:
        session["contracts_session_marker"] = "session-2"

    with patch("routers.contracts.ContractsFlowService.get_flow", return_value=None):
        response = await client.get("/contracts/flow/req-1/status")

    assert response.status_code == 404
    assert await response.get_json() == {"ok": False, "error": "Flow not found"}


@pytest.mark.asyncio
async def test_message_action_returns_latest_message_json(client):
    with (
        patch(
            "routers.contracts.load_message",
            new=AsyncMock(
                return_value={"ok": True, "message": "Long live the king", "error": ""}
            ),
        ),
        patch(
            "routers.contracts.notify_mountain_message_change",
            new=AsyncMock(
                return_value={"created": False, "reason": "grist", "error": ""}
            ),
        ) as notify_mock,
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}/actions/message")

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "message": "Long live the king",
        "error": "",
    }
    notify_mock.assert_awaited_once_with("Long live the king")


@pytest.mark.asyncio
async def test_range_action_returns_latest_range_json(client):
    with patch(
        "routers.contracts.load_range",
        new=AsyncMock(
            return_value={
                "ok": True,
                "min_amount_raw": "10000000",
                "max_amount_raw": "25000000",
                "min_amount_eurmtl": "1",
                "max_amount_eurmtl": "2.5",
                "error": "",
            }
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}/actions/range")

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "min_amount_raw": "10000000",
        "max_amount_raw": "25000000",
        "min_amount_eurmtl": "1",
        "max_amount_eurmtl": "2.5",
        "error": "",
    }


@pytest.mark.asyncio
async def test_swap_estimate_action_returns_human_readable_quote(client):
    with patch(
        "routers.contracts.estimate_swap_exact_in",
        new=AsyncMock(
            return_value={
                "ok": True,
                "amount_in": "1",
                "estimated_out": "0.8364215",
                "from_token": "USDM",
                "to_token": "EURMTL",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{SWAP_CONTRACT_ID}/actions/estimate-swap",
            form={"direction": "USDM_TO_EURMTL", "amount_in": "1"},
        )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "amount_in": "1",
        "estimated_out": "0.8364215",
        "from_token": "USDM",
        "to_token": "EURMTL",
    }


@pytest.mark.asyncio
async def test_swap_prepare_action_returns_request_id_uri_and_stores_last_used_address(
    client,
):
    with patch(
        "routers.contracts.prepare_swap_flow",
        new=AsyncMock(
            return_value={
                "request_id": "swap-req-1",
                "uri": "web+stellar:tx?xdr=AAAA",
                "qr_url": "/static/qr/swap-req-1.png",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{SWAP_CONTRACT_ID}/actions/swap/prepare",
            form={
                "user": VALID_USER,
                "direction": "USDM_TO_EURMTL",
                "amount_in": "1",
                "slippage": "1",
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "request_id": "swap-req-1",
        "uri": "web+stellar:tx?xdr=AAAA",
        "qr_url": "/static/qr/swap-req-1.png",
        "qr_error": "",
    }
    async with client.session_transaction() as session:
        assert session["contracts_last_used_address"] == VALID_USER


@pytest.mark.asyncio
async def test_swap_strict_receive_prepare_action_returns_request_id_uri(client):
    with patch(
        "routers.contracts.prepare_swap_flow",
        new=AsyncMock(
            return_value={
                "request_id": "swap-req-2",
                "uri": "web+stellar:tx?xdr=BBBB",
                "qr_url": "/static/qr/swap-req-2.png",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{SWAP_CONTRACT_ID}/actions/swap-strict-receive/prepare",
            form={
                "user": VALID_USER,
                "direction": "USDM_TO_EURMTL",
                "amount_out": "1",
                "slippage": "3",
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "request_id": "swap-req-2",
        "uri": "web+stellar:tx?xdr=BBBB",
        "qr_url": "/static/qr/swap-req-2.png",
        "qr_error": "",
    }


@pytest.mark.asyncio
async def test_swap_prepare_action_returns_uri_even_when_qr_generation_fails(client):
    with (
        patch(
            "routers.contracts.prepare_swap_exact_in_flow",
            new=AsyncMock(
                return_value={"uri": "web+stellar:tx?xdr=LONG", "xdr": "AAAA"}
            ),
        ),
        patch(
            "routers.contracts.ContractsFlowService.create_flow",
            return_value={
                "request_id": "swap-req-long",
                "session_marker": "session-1",
                "contract_id": SWAP_CONTRACT_ID,
                "action_name": "swap",
                "form_data": {},
                "status": "created",
                "tx_hash": "",
                "error_message": "",
                "signed_xdr": "",
                "unsigned_xdr": "",
                "uri": "",
                "qr_url": "",
            },
        ),
        patch(
            "routers.contracts.create_beautiful_code",
            side_effect=ValueError("Invalid version (was 41, expected 1 to 40)"),
        ),
    ):
        response = await client.post(
            f"/contracts/{SWAP_CONTRACT_ID}/actions/swap/prepare",
            form={
                "user": VALID_USER,
                "direction": "USDM_TO_EURMTL",
                "amount_in": "1",
                "slippage": "5",
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "request_id": "swap-req-long",
        "uri": "web+stellar:tx?xdr=LONG",
        "qr_url": "",
        "qr_error": "URI too long for QR generation",
    }


@pytest.mark.asyncio
async def test_swap_prepare_action_rejects_invalid_payload(client):
    response = await client.post(
        f"/contracts/{SWAP_CONTRACT_ID}/actions/swap/prepare",
        form={
            "user": "",
            "direction": "USDM_TO_EURMTL",
            "amount_in": "0",
            "slippage": "1",
        },
    )

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "error": "user and amount are required",
    }


@pytest.mark.asyncio
async def test_swap_strict_receive_estimate_action_returns_human_readable_quote(client):
    with patch(
        "routers.contracts.estimate_swap_exact_out",
        new=AsyncMock(
            return_value={
                "ok": True,
                "amount_out": "1",
                "estimated_in": "1.1948132",
                "from_token": "USDM",
                "to_token": "EURMTL",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{SWAP_CONTRACT_ID}/actions/estimate-swap-strict-receive",
            form={"direction": "USDM_TO_EURMTL", "amount_out": "1"},
        )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "amount_out": "1",
        "estimated_in": "1.1948132",
        "from_token": "USDM",
        "to_token": "EURMTL",
    }


@pytest.mark.asyncio
async def test_contract_detail_renders_interactive_contract_ui(client):
    with (
        patch(
            "routers.contracts.load_message",
            new=AsyncMock(
                return_value={"ok": True, "message": "Live message", "error": ""}
            ),
        ),
        patch(
            "routers.contracts.load_range",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "min_amount_raw": "10000000",
                    "max_amount_raw": "25000000",
                    "min_amount_eurmtl": "1",
                    "max_amount_eurmtl": "2.5",
                    "error": "",
                }
            ),
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    body = await response.get_data(as_text=True)
    assert 'id="message-refresh-button"' in body
    assert 'id="capture-form"' in body
    assert 'id="contractsSep7QrImg"' in body
    assert 'id="contractsFlowStatus"' in body
    assert 'id="contractsResult"' in body
    assert "Use my address" in body
    assert 'id="range-result"' in body
    assert "refreshRange" in body
    assert "addEventListener" not in body
    assert 'onclick="refreshMountainState()"' in body
    assert 'onclick="fillCurrentUserAddress()"' in body
    assert 'onsubmit="submitCaptureForm(event)"' in body
    assert "Loading latest contract state..." in body
    assert "Could not fill your address automatically." in body


@pytest.mark.asyncio
async def test_contract_detail_use_my_address_button_uses_prefill_user(client):
    async with client.session_transaction() as session:
        session["contracts_last_used_address"] = VALID_USER

    with patch(
        "routers.contracts.load_range",
        new=AsyncMock(
            return_value={
                "ok": True,
                "min_amount_raw": "10000000",
                "max_amount_raw": "25000000",
                "min_amount_eurmtl": "1",
                "max_amount_eurmtl": "2.5",
                "error": "",
            }
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    body = await response.get_data(as_text=True)
    assert f"const prefillUser = {VALID_USER!r};".replace("'", '"') in body
    assert "prefillUser || detectedAddress || ''" in body


@pytest.mark.asyncio
async def test_mountain_contract_detail_disables_capture_when_range_loading_fails(
    client,
):
    with patch(
        "routers.contracts.load_range",
        new=AsyncMock(
            return_value={
                "ok": False,
                "min_amount_raw": "",
                "max_amount_raw": "",
                "min_amount_eurmtl": "",
                "max_amount_eurmtl": "",
                "error": "range unavailable",
            }
        ),
    ):
        response = await client.get(f"/contracts/{FIRST_CONTRACT_ID}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "range unavailable" in body
    assert 'id="capture-submit-button"' in body
    assert "disabled" in body


@pytest.mark.asyncio
async def test_capture_prepare_rejects_out_of_range_amount(client):
    with patch(
        "routers.contracts.load_range",
        new=AsyncMock(
            return_value={
                "ok": True,
                "min_amount_raw": "10",
                "max_amount_raw": "20",
                "min_amount_eurmtl": "0.000001",
                "max_amount_eurmtl": "0.000002",
                "error": "",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{FIRST_CONTRACT_ID}/actions/capture/prepare",
            form={"user": VALID_USER, "amount": "9", "msg": "For glory"},
        )

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "error": "amount must be between 10 and 20 raw units",
    }


@pytest.mark.asyncio
async def test_capture_prepare_rejects_when_range_lookup_fails(client):
    with patch(
        "routers.contracts.load_range",
        new=AsyncMock(
            return_value={
                "ok": False,
                "min_amount_raw": "",
                "max_amount_raw": "",
                "min_amount_eurmtl": "",
                "max_amount_eurmtl": "",
                "error": "range unavailable",
            }
        ),
    ):
        response = await client.post(
            f"/contracts/{FIRST_CONTRACT_ID}/actions/capture/prepare",
            form={"user": VALID_USER, "amount": "10", "msg": "For glory"},
        )

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "error": "range unavailable",
    }


@pytest.mark.asyncio
async def test_contracts_send_page_renders_hidden_submit_form(client):
    response = await client.get("/contracts/send")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Contracts Send" in body
    assert 'name="signed_xdr"' in body
    assert "Hidden helper page" in body


@pytest.mark.asyncio
async def test_contracts_send_page_submits_signed_xdr_and_renders_result(client):
    with patch(
        "routers.contracts.submit_signed_transaction",
        new=AsyncMock(return_value={"ok": True, "tx_hash": "abc123", "error": ""}),
    ):
        response = await client.post(
            "/contracts/send",
            form={"signed_xdr": "AAAAAA=="},
        )

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "abc123" in body
    assert "submitted" in body
    assert "Open in Stellar Expert" in body


@pytest.mark.asyncio
async def test_contracts_send_page_renders_validation_error(client):
    response = await client.post(
        "/contracts/send",
        form={"signed_xdr": "bad!!!"},
    )

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Invalid or missing base64 data" in body


@pytest.mark.asyncio
async def test_contracts_flow_mmwb_returns_generated_bot_link(client):
    async with client.session_transaction() as session:
        session["contracts_session_marker"] = "session-1"

    with (
        patch(
            "routers.contracts.ContractsFlowService.get_flow",
            return_value={"request_id": "req-1", "uri": "web+stellar:tx?xdr=AAAA"},
        ),
        patch(
            "routers.contracts.http_session_manager.get_web_request",
            new=AsyncMock(
                return_value=type(
                    "Resp",
                    (),
                    {
                        "status": 200,
                        "data": {
                            "SUCCESS": True,
                            "url": "https://t.me/MyMTLWalletBot?start=uri_abc",
                        },
                    },
                )()
            ),
        ),
    ):
        response = await client.post("/contracts/flow/req-1/mmwb")

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "url": "https://t.me/MyMTLWalletBot?start=uri_abc",
    }


@pytest.mark.asyncio
async def test_contracts_flow_mmwb_rejects_unknown_flow(client):
    async with client.session_transaction() as session:
        session["contracts_session_marker"] = "session-1"

    with patch("routers.contracts.ContractsFlowService.get_flow", return_value=None):
        response = await client.post("/contracts/flow/missing/mmwb")

    assert response.status_code == 404
    assert await response.get_json() == {"ok": False, "error": "Flow not found"}


@pytest.mark.asyncio
async def test_contracts_callback_marks_flow_submitted_when_submit_succeeds(client):
    flow = {
        "request_id": "req-1",
        "status": "created",
        "tx_hash": "",
        "error_message": "",
        "signed_xdr": "",
    }

    with patch("routers.contracts.is_valid_base64", return_value=True):
        with patch(
            "routers.contracts.ContractsFlowService.get_flow_for_callback",
            return_value=flow,
        ):
            with patch(
                "routers.contracts.submit_signed_transaction",
                new=AsyncMock(
                    return_value={"ok": True, "tx_hash": "abc123", "error": ""}
                ),
            ):
                with patch(
                    "routers.contracts.ContractsFlowService.update_flow_result",
                    return_value={
                        **flow,
                        "status": "submitted",
                        "tx_hash": "abc123",
                        "error_message": "",
                        "signed_xdr": "AAAAAA==",
                    },
                ):
                    response = await client.post(
                        "/contracts/callback/req-1",
                        form={"xdr": "AAAAAA=="},
                    )

    assert response.status_code == 200
    assert await response.get_json() == {
        "ok": True,
        "status": "submitted",
        "tx_hash": "abc123",
    }


@pytest.mark.asyncio
async def test_contracts_callback_stores_failure_payload_when_submit_fails(client):
    flow = {
        "request_id": "req-1",
        "status": "created",
        "tx_hash": "",
        "error_message": "",
        "signed_xdr": "",
    }

    with patch("routers.contracts.is_valid_base64", return_value=True):
        with patch(
            "routers.contracts.ContractsFlowService.get_flow_for_callback",
            return_value=flow,
        ):
            with patch(
                "routers.contracts.submit_signed_transaction",
                new=AsyncMock(
                    return_value={"ok": False, "tx_hash": "", "error": "submit failed"}
                ),
            ):
                with patch(
                    "routers.contracts.ContractsFlowService.update_flow_result",
                    return_value={
                        **flow,
                        "status": "failed",
                        "tx_hash": "",
                        "error_message": "submit failed",
                        "signed_xdr": "AAAAAA==",
                    },
                ):
                    response = await client.post(
                        "/contracts/callback/req-1",
                        form={"xdr": "AAAAAA=="},
                    )

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "status": "failed",
        "error": "submit failed",
    }


@pytest.mark.asyncio
async def test_contracts_callback_rejects_malformed_base64(client):
    response = await client.post("/contracts/callback/req-1", form={"xdr": "bad!!!"})

    assert response.status_code == 400
    assert await response.get_json() == {
        "ok": False,
        "error": "Invalid or missing base64 data",
    }


@pytest.mark.asyncio
async def test_contracts_callback_rejects_unknown_or_foreign_flow(client):
    with patch("routers.contracts.is_valid_base64", return_value=True):
        with patch(
            "routers.contracts.ContractsFlowService.get_flow_for_callback",
            return_value=None,
        ):
            response = await client.post(
                "/contracts/callback/req-1", form={"xdr": "AAAAAA=="}
            )

    assert response.status_code == 404
    assert await response.get_json() == {"ok": False, "error": "Flow not found"}
