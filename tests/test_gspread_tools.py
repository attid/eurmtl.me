from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from other.gspread_tools import (
    get_creds,
    gs_get_asset,
    gs_get_decision,
    gs_get_last_id,
    gs_save_new_decision,
    gs_update_decision,
)


def test_get_creds_builds_scoped_credentials():
    creds = MagicMock()
    creds.with_scopes.return_value = "scoped"

    with patch(
        "other.gspread_tools.Credentials.from_service_account_file",
        return_value=creds,
    ) as from_file:
        result = get_creds()

    assert result == "scoped"
    from_file.assert_called_once()
    creds.with_scopes.assert_called_once()


def _build_sheet_stack():
    worksheet = AsyncMock()
    spreadsheet = AsyncMock()
    client = AsyncMock()

    spreadsheet.worksheet.return_value = worksheet
    client.open.return_value = spreadsheet
    return client, spreadsheet, worksheet


@pytest.mark.asyncio
async def test_gspread_helpers_cover_read_write_paths():
    client, _spreadsheet, worksheet = _build_sheet_stack()
    worksheet.col_values.return_value = ["1", "2", "3"]
    worksheet.find.side_effect = [
        type("Cell", (), {"row": 4})(),
        type("Cell", (), {"row": 7})(),
    ]
    worksheet.row_values.return_value = ["155", "Decision", "url"]

    with patch("other.gspread_tools.agcm.authorize", AsyncMock(return_value=client)):
        assert await gs_get_last_id() == (3, 3)
        await gs_save_new_decision("10", "Short", "https://t.me/x", "@user")
        assert await gs_get_decision(155) == ["155", "Decision", "url"]
        await gs_update_decision(155, 6, "https://t.me/new")

    worksheet.update.assert_awaited_once()
    worksheet.update_cell.assert_awaited_once_with(
        row=7, col=6, value="https://t.me/new"
    )


@pytest.mark.asyncio
async def test_gs_get_asset_returns_issuer_only_for_qr_enabled_asset():
    client, _spreadsheet, worksheet = _build_sheet_stack()
    worksheet.find.return_value = type("Cell", (), {"row": 2})()
    worksheet.row_values.return_value = [""] * 14
    worksheet.row_values.return_value[5] = "ISSUER"
    worksheet.row_values.return_value[13] = "TRUE"

    with patch("other.gspread_tools.agcm.authorize", AsyncMock(return_value=client)):
        assert await gs_get_asset("EURMTL") == "ISSUER"

    worksheet.row_values.return_value[13] = "FALSE"
    with patch("other.gspread_tools.agcm.authorize", AsyncMock(return_value=client)):
        assert await gs_get_asset("EURMTL") is None
