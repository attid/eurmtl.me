from services.contracts.flow_service import ContractsFlowService


def test_create_flow_returns_request_id_and_stores_metadata():
    service = ContractsFlowService()

    flow = service.create_flow(
        session_marker="session-1",
        contract_id="CID",
        action_name="capture",
        form_data={"user": "GABC", "amount": "10", "msg": "hi"},
    )

    assert flow["request_id"]
    stored = service.get_flow(flow["request_id"], session_marker="session-1")
    assert stored["contract_id"] == "CID"
    assert stored["action_name"] == "capture"
    assert stored["form_data"] == {"user": "GABC", "amount": "10", "msg": "hi"}
    assert stored["status"] == "created"


def test_get_flow_is_scoped_to_originating_session_marker():
    service = ContractsFlowService()
    flow = service.create_flow(
        session_marker="session-1",
        contract_id="CID",
        action_name="capture",
        form_data={},
    )

    assert service.get_flow(flow["request_id"], session_marker="session-2") is None


def test_get_flow_for_callback_ignores_browser_session_scope():
    service = ContractsFlowService()
    flow = service.create_flow(
        session_marker="session-1",
        contract_id="CID",
        action_name="capture",
        form_data={},
    )

    assert (
        service.get_flow_for_callback(flow["request_id"])["request_id"]
        == flow["request_id"]
    )


def test_update_flow_result_stores_status_hash_and_error_fields():
    service = ContractsFlowService()
    flow = service.create_flow(
        session_marker="session-1",
        contract_id="CID",
        action_name="capture",
        form_data={},
    )

    updated = service.update_flow_result(
        flow["request_id"],
        status="submitted",
        tx_hash="abc123",
        error_message="",
        signed_xdr="AAAA",
    )

    assert updated["status"] == "submitted"
    assert updated["tx_hash"] == "abc123"
    assert updated["error_message"] == ""
    assert updated["signed_xdr"] == "AAAA"


def test_pick_prefill_address_prefers_detected_then_last_used_then_empty():
    assert (
        ContractsFlowService.pick_prefill_address(
            detected_address="GDETECTED",
            last_used_address="GLAST",
        )
        == "GDETECTED"
    )
    assert (
        ContractsFlowService.pick_prefill_address(
            detected_address="",
            last_used_address="GLAST",
        )
        == "GLAST"
    )
    assert (
        ContractsFlowService.pick_prefill_address(
            detected_address=None,
            last_used_address=None,
        )
        == ""
    )
