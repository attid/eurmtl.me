from __future__ import annotations

from uuid import uuid4

from cachetools import TTLCache


class ContractsFlowService:
    _store = TTLCache(maxsize=512, ttl=60 * 30)

    def __init__(self) -> None:
        self.store = self.__class__._store

    def create_flow(
        self,
        session_marker: str,
        contract_id: str,
        action_name: str,
        form_data: dict,
    ) -> dict:
        request_id = uuid4().hex
        flow = {
            "request_id": request_id,
            "session_marker": session_marker,
            "contract_id": contract_id,
            "action_name": action_name,
            "form_data": dict(form_data),
            "status": "created",
            "tx_hash": "",
            "error_message": "",
            "signed_xdr": "",
            "unsigned_xdr": "",
            "uri": "",
            "qr_url": "",
        }
        self.store[request_id] = flow
        return flow

    def get_flow(self, request_id: str, session_marker: str) -> dict | None:
        flow = self.store.get(request_id)
        if flow is None:
            return None
        if flow["session_marker"] != session_marker:
            return None
        return flow

    def get_flow_for_callback(self, request_id: str) -> dict | None:
        return self.store.get(request_id)

    def update_flow_result(
        self,
        request_id: str,
        *,
        status: str,
        tx_hash: str,
        error_message: str,
        signed_xdr: str,
    ) -> dict | None:
        flow = self.store.get(request_id)
        if flow is None:
            return None
        flow.update(
            {
                "status": status,
                "tx_hash": tx_hash,
                "error_message": error_message,
                "signed_xdr": signed_xdr,
            }
        )
        return flow

    def update_flow_prepare_data(
        self,
        request_id: str,
        *,
        unsigned_xdr: str,
        uri: str,
        qr_url: str,
    ) -> dict | None:
        flow = self.store.get(request_id)
        if flow is None:
            return None
        flow.update(
            {
                "unsigned_xdr": unsigned_xdr,
                "uri": uri,
                "qr_url": qr_url,
            }
        )
        return flow

    @staticmethod
    def pick_prefill_address(
        detected_address: str | None,
        last_used_address: str | None,
    ) -> str:
        if detected_address:
            return detected_address
        if last_used_address:
            return last_used_address
        return ""
