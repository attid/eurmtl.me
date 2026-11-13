"""Живые e2e-тесты лабы против публичного Horizon.

ВРЕМЕННО: отдельный набор с гейтом `RUN_LIVE_TESTS=1` + `just test-live`.
Целевое состояние (владелец): никакого отдельного `live`-набора и гейта —
всё идёт одним `just test`, моки вырезаны. При слиянии: убрать `pytestmark`
с `skipif`, маркер `live` в `pytest.ini` и рецепт `test-live` в `justfile`.

Только чтение: path discovery и `load_account` — GET-запросы. Транзакции
никогда не отправляются (`submit`), поэтому тесты безопасны на mainnet.
"""

import json
import os

import pytest
from stellar_sdk import Network, PathPaymentStrictReceive, TransactionEnvelope

from services.stellar_client import main_fund_address

pytestmark = [
    # ВРЕМЕННО до слияния в общий `just test`: см. docstring модуля.
    pytest.mark.live,
    pytest.mark.skipif(
        not os.getenv("RUN_LIVE_TESTS"),
        reason="живой Horizon: запускать с RUN_LIVE_TESTS=1",
    ),
]

# Публичный аккаунт фонда (единственный источник правды — stellar_client).
FUND_ACCOUNT = main_fund_address
# EURMTL выпускается фондом; код длиннее 4 символов -> credit_alphanum12.
EURMTL = f"EURMTL-{FUND_ACCOUNT}"
RECEIVE_AMOUNT = "10"


@pytest.mark.asyncio
async def test_live_path_receive_returns_paths_with_send_max(client):
    """strict_receive_paths через реальный Horizon: путь + сумма отправки.

    Регресс на P1 из ревью: одиночный Asset вместо списка давал TypeError и
    пустой ответ, который моки не ловили.
    """
    response = await client.get(
        f"/lab/path_receive/XLM/{EURMTL}/{RECEIVE_AMOUNT}",
    )

    assert response.status_code == 200
    result = await response.get_json()
    assert result, "Horizon должен вернуть хотя бы один путь XLM -> EURMTL"

    label, payload = next(iter(result.items()))
    assert label.startswith("send ")
    assert "XLM" in label
    parsed = json.loads(payload)
    assert float(parsed["send_max"]) > 0
    assert isinstance(parsed["path"], list)


@pytest.mark.asyncio
async def test_live_path_receive_and_path_use_different_amount_semantics(client):
    """strict send считает сумму отправки, strict receive — сумму получения."""
    receive = await client.get(f"/lab/path_receive/XLM/{EURMTL}/{RECEIVE_AMOUNT}")
    send = await client.get(f"/lab/path/XLM/{EURMTL}/{RECEIVE_AMOUNT}")

    receive_result = await receive.get_json()
    send_result = await send.get_json()

    assert receive_result and send_result
    # receive: "send <сумма отправки> XLM ...", send: "<сумма получения> EURMTL"
    assert next(iter(receive_result)).startswith("send ")
    assert next(iter(send_result)).endswith("EURMTL")
    assert set(receive_result) != set(send_result)


@pytest.mark.asyncio
async def test_live_path_returns_destination_amounts(client):
    """/lab/path (strict send): живой Horizon отдает пути и сумму к получению."""
    response = await client.get(f"/lab/path/XLM/{EURMTL}/{RECEIVE_AMOUNT}")

    assert response.status_code == 200
    result = await response.get_json()
    assert result, "Horizon должен вернуть хотя бы один путь XLM -> EURMTL"

    for label, path_json in result.items():
        assert label.endswith("EURMTL")
        assert float(label.split(" ")[0]) > 0
        assert isinstance(json.loads(path_json), list)


@pytest.mark.asyncio
async def test_live_build_swap_strict_receive_with_custom_source_account(client):
    """sourceAccount операции — и источник, и получатель (D2: шлём себе)."""
    operation = {
        "type": "swap_strict_receive",
        "selling": "XLM",
        "buying": EURMTL,
        "amount": "1",
        "destination": "3",
        "path": "[]",
        "sourceAccount": FUND_ACCOUNT,
    }

    built = await client.post(
        "/lab/build_xdr",
        json={"publicKey": FUND_ACCOUNT, "operations": [operation]},
    )
    assert built.status_code == 200, await built.get_json()

    built_operation = TransactionEnvelope.from_xdr(
        (await built.get_json())["xdr"], Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction.operations[0]

    assert isinstance(built_operation, PathPaymentStrictReceive)
    assert built_operation.source.account_id == FUND_ACCOUNT
    assert built_operation.destination.account_id == FUND_ACCOUNT


@pytest.mark.asyncio
async def test_live_build_swap_strict_receive_xdr_round_trip(client):
    """Сборка XDR на живом аккаунте -> декод -> повторная сборка."""
    operation = {
        "type": "swap_strict_receive",
        "selling": "XLM",
        "buying": EURMTL,
        "amount": RECEIVE_AMOUNT,
        "destination": "20",
        "path": "[]",
    }

    built = await client.post(
        "/lab/build_xdr",
        json={"publicKey": FUND_ACCOUNT, "operations": [operation]},
    )
    assert built.status_code == 200, await built.get_json()
    xdr = (await built.get_json())["xdr"]

    decoded_operation = TransactionEnvelope.from_xdr(
        xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction.operations[0]
    assert isinstance(decoded_operation, PathPaymentStrictReceive)
    assert decoded_operation.destination.account_id == FUND_ACCOUNT
    assert decoded_operation.dest_amount == RECEIVE_AMOUNT
    assert decoded_operation.send_max == "20"
    assert decoded_operation.dest_asset.code == "EURMTL"

    decoded = await client.post("/lab/xdr_to_json", json={"xdr": xdr})
    assert decoded.status_code == 200
    decoded_json = await decoded.get_json()
    lab_operation = decoded_json["operations"][0]
    assert lab_operation["name"] == "swap_strict_receive"
    attrs = lab_operation["attributes"]

    rebuilt = await client.post(
        "/lab/build_xdr",
        json={
            "publicKey": FUND_ACCOUNT,
            "operations": [
                {
                    "type": "swap_strict_receive",
                    "selling": "XLM"
                    if attrs["selling"]["type"] == "native"
                    else f"{attrs['selling']['code']}-{attrs['selling']['issuer']}",
                    "buying": f"{attrs['buying']['code']}-{attrs['buying']['issuer']}",
                    "amount": attrs["amount"],
                    "destination": attrs["destination"],
                    "path": attrs["path"],
                }
            ],
        },
    )
    assert rebuilt.status_code == 200, await rebuilt.get_json()

    rebuilt_operation = TransactionEnvelope.from_xdr(
        (await rebuilt.get_json())["xdr"], Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction.operations[0]
    assert isinstance(rebuilt_operation, PathPaymentStrictReceive)
    assert rebuilt_operation.dest_amount == decoded_operation.dest_amount
    assert rebuilt_operation.send_max == decoded_operation.send_max
    assert rebuilt_operation.dest_asset == decoded_operation.dest_asset


@pytest.mark.asyncio
async def test_live_decoded_text_shows_receive_and_send_sides(client):
    """Текстовый декод: получаем buying, шлём максимум selling."""
    built = await client.post(
        "/lab/build_xdr",
        json={
            "publicKey": FUND_ACCOUNT,
            "operations": [
                {
                    "type": "swap_strict_receive",
                    "selling": "XLM",
                    "buying": EURMTL,
                    "amount": RECEIVE_AMOUNT,
                    "destination": "20",
                    "path": "[]",
                }
            ],
        },
    )
    xdr = (await built.get_json())["xdr"]

    decoded = await client.post("/remote/decode", json={"xdr": xdr})
    assert decoded.status_code == 200
    text = (await decoded.get_json())["text"]

    assert "PathPaymentStrictReceive" in text
    assert "получаем" in text
    assert "EURMTL" in text
    assert "шлём" in text
    assert "max 20" in text


@pytest.mark.asyncio
async def test_live_path_receive_bad_asset_returns_empty_dict(client):
    """Мусорный asset не должен давать 500 (как и у /lab/path)."""
    response = await client.get(f"/lab/path_receive/INVALID/{EURMTL}/{RECEIVE_AMOUNT}")

    assert response.status_code == 200
    assert await response.get_json() == {}
