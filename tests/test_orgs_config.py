"""orgs_config: уникальность имён, каналы PFM, валидация конфига."""

import pytest

from other import orgs_config
from other.orgs_config import Org, _validate


def test_org_names_unique():
    names = [org.name for org in orgs_config.ORGS]
    assert len(names) == len(set(names))
    assert all(names)


def test_pfm_channels_match_first_fund_chat_id():
    assert orgs_config.DEFAULT_ORG_NAME == "PFM"
    pfm = next(org for org in orgs_config.ORGS if org.name == "PFM")
    assert pfm.channels == ("1863399780", "1652080456", "1649743884")
    # Паритет с fallback-константой фонда: ловит расхождение при правке
    # DEFAULT_FUND_CHAT_IDS в grist_tools без обновления конфига.
    from other.grist_tools import DEFAULT_FUND_CHAT_IDS

    assert pfm.channels == tuple(str(chat_id) for chat_id in DEFAULT_FUND_CHAT_IDS[1:])


def test_pfm_main_address_is_fund_address():
    from services.stellar_client import main_fund_address

    pfm = next(org for org in orgs_config.ORGS if org.name == "PFM")
    assert pfm.main_address == main_fund_address


def test_validate_rejects_duplicate_name():
    orgs = (
        Org("PFM", "GACKTN", ("1",), 1),
        Org("PFM", "GORAADDR", ("2",), 1),
    )
    with pytest.raises(ValueError, match="дубликат"):
        _validate(orgs)


def test_validate_rejects_empty_name():
    orgs = (Org("", "GACKTN", ("1",), 1),)
    with pytest.raises(ValueError, match="пустым"):
        _validate(orgs)


def test_validate_rejects_address_without_channels():
    orgs = (Org("TFM", "GACKTN", (), 1),)
    with pytest.raises(ValueError, match="каналы"):
        _validate(orgs)


def test_validate_rejects_negative_readings():
    orgs = (Org("TFM", "", (), -1),)
    with pytest.raises(ValueError, match="readings"):
        _validate(orgs)


def test_validate_allows_stub_without_address():
    """TFM-заглушка (пустой адрес без каналов) легитимна."""
    _validate((Org("TFM", "", (), 0),))
