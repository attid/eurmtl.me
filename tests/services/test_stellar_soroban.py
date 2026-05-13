import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from other.stellar_soroban import (
    read_contract_string,
    read_token_contract_display_name,
    submit_signed_transaction,
)


@pytest.mark.asyncio
async def test_read_contract_string_uses_json_rpc_simulation_payload():
    with patch(
        "other.stellar_soroban._post_json_rpc",
        new=AsyncMock(
            return_value={
                "status": 200,
                "data": {
                    "result": {
                        "results": [
                            {
                                "returnValueJson": {
                                    "string": "Long live the king",
                                }
                            }
                        ]
                    }
                },
            }
        ),
    ) as request_mock:
        result = await read_contract_string(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id="CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM",
            function_name="message",
        )

    assert result == "Long live the king"
    request_mock.assert_awaited_once()
    args, _ = request_mock.call_args
    assert args[0] == "https://soroban-rpc.mainnet.stellar.gateway.fm"
    assert args[1]["method"] == "simulateTransaction"
    assert args[1]["params"]["xdrFormat"] == "json"
    assert args[1]["params"]["authMode"] == ""


@pytest.mark.asyncio
async def test_read_contract_string_decodes_escaped_utf8_string_payload():
    with patch(
        "other.stellar_soroban._post_json_rpc",
        new=AsyncMock(
            return_value={
                "status": 200,
                "data": {
                    "result": {
                        "results": [
                            {
                                "returnValueJson": {
                                    "string": "\\xd0\\x99\\xd1\\x83\\xd0\\xa5",
                                }
                            }
                        ]
                    }
                },
            }
        ),
    ):
        result = await read_contract_string(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id="CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM",
            function_name="message",
        )

    assert result == "ЙуХ"


@pytest.mark.asyncio
async def test_read_contract_string_supports_base64_result_fallback():
    with patch(
        "other.stellar_soroban._post_json_rpc",
        new=AsyncMock(
            return_value={
                "status": 200,
                "data": {
                    "result": {
                        "results": [
                            {
                                "xdr": "AAAADgAAABYtLS0gTm8gbWVzc2FnZSB5ZXQgLS0tAAA=",
                            }
                        ]
                    }
                },
            }
        ),
    ):
        result = await read_contract_string(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id="CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM",
            function_name="message",
        )

    assert result == "--- No message yet ---"


@pytest.mark.asyncio
async def test_read_contract_string_surfaces_clean_errors():
    with patch(
        "other.stellar_soroban._post_json_rpc",
        new=AsyncMock(side_effect=RuntimeError("rpc down")),
    ):
        with pytest.raises(ValueError, match="rpc down"):
            await read_contract_string(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                contract_id="CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM",
                function_name="message",
            )


@pytest.mark.asyncio
async def test_read_token_contract_display_name_normalizes_and_caches_result():
    with patch(
        "other.stellar_soroban.read_contract_string",
        new=AsyncMock(
            return_value="EURMTL:GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
        ),
    ) as read_string_mock:
        first = await read_token_contract_display_name(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id="CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK",
        )
        second = await read_token_contract_display_name(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id="CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK",
        )

    assert first == "EURMTL"
    assert second == "EURMTL"
    read_string_mock.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_read_token_contract_display_name_live_eurmtl_contract():
    result = await read_token_contract_display_name(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        contract_id="CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK",
    )

    assert result == "EURMTL"


@pytest.mark.asyncio
async def test_prepare_contract_transaction_uri_uses_future_approve_expiration_and_5_min_timeout():
    with patch("other.stellar_soroban.SorobanServer") as server_cls:
        server = server_cls.return_value
        server.load_account.return_value = MagicMock()
        server.get_latest_ledger.return_value = MagicMock(sequence=62090711)
        prepared_transaction = MagicMock()
        prepared_transaction.to_xdr.return_value = "AAAA"
        server.prepare_transaction.return_value = prepared_transaction

        with patch(
            "other.stellar_soroban._post_json_rpc",
            new=AsyncMock(return_value={"status": 200, "data": {"result": {}}}),
        ):
            with patch(
                "other.stellar_soroban.stellar_uri.TransactionStellarUri"
            ) as uri_cls:
                uri = uri_cls.return_value
                uri.to_uri.return_value = "web+stellar:tx?xdr=AAAA"

                await __import__(
                    "other.stellar_soroban"
                ).stellar_soroban.prepare_contract_transaction_uri(
                    rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                    contract_id="CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM",
                    function_name="capture",
                    source_account_id="GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
                    parameters=[MagicMock(), MagicMock(), MagicMock()],
                    callback_url="https://eurmtl.me/contracts/callback/123",
                    message="Capture the mountain",
                    origin_domain="eurmtl.me",
                    signer_secret="SBADSECRET",
                    token_contract_id="CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK",
                    approve_expiration_ledger_offset=1000,
                )

    server.get_latest_ledger.assert_called_once()
    prepared_call = server.prepare_transaction.call_args.args[0]
    assert prepared_call.transaction.preconditions.time_bounds.max_time > 0


@pytest.mark.asyncio
async def test_submit_signed_transaction_returns_decoded_error_when_send_fails():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(
                status="ERROR",
                hash="abc123",
                error_result_xdr="AAAAAAABLML////9AAAAAA==",
            )

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {
        "ok": False,
        "tx_hash": "abc123",
        "error": "Sending transaction failed: txTOO_LATE",
    }


@pytest.mark.asyncio
async def test_submit_signed_transaction_returns_hash_when_non_pending_send_already_has_hash_and_later_succeeds():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(
                status="ERROR", hash="abc123", error_result_xdr=None
            )
            server.get_transaction.side_effect = [
                MagicMock(status="NOT_FOUND"),
                MagicMock(status="SUCCESS"),
            ]

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {"ok": True, "tx_hash": "abc123", "error": ""}


class _EnumLikeStatus:
    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return f"Status.{self.name}"


@pytest.mark.asyncio
async def test_submit_signed_transaction_handles_enum_like_status_values():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(
                status=_EnumLikeStatus("PENDING"), hash="abc123"
            )
            server.get_transaction.side_effect = [
                MagicMock(status=_EnumLikeStatus("NOT_FOUND")),
                MagicMock(status=_EnumLikeStatus("SUCCESS")),
            ]

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {"ok": True, "tx_hash": "abc123", "error": ""}


@pytest.mark.asyncio
async def test_submit_signed_transaction_returns_hash_on_success():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(
                status="PENDING", hash="abc123"
            )
            server.get_transaction.side_effect = [
                MagicMock(status="NOT_FOUND"),
                MagicMock(status="SUCCESS"),
            ]

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {"ok": True, "tx_hash": "abc123", "error": ""}


@pytest.mark.asyncio
async def test_submit_signed_transaction_returns_hash_when_status_is_still_pending_after_polling():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(
                status="PENDING", hash="abc123"
            )
            server.get_transaction.return_value = MagicMock(status="NOT_FOUND")

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {"ok": True, "tx_hash": "abc123", "error": ""}


@pytest.mark.asyncio
async def test_submit_signed_transaction_returns_error_when_send_fails():
    with patch("other.stellar_soroban.TransactionEnvelope.from_xdr", return_value="TX"):
        with patch("other.stellar_soroban.SorobanServer") as server_cls:
            server = server_cls.return_value
            server.send_transaction.return_value = MagicMock(status="ERROR", hash="")

            result = await submit_signed_transaction(
                rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
                signed_xdr="AAAAAA==",
            )

    assert result == {"ok": False, "tx_hash": "", "error": "Sending transaction failed"}
