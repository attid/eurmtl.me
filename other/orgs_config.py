"""Организации D2: конфиг в коде вместо Grist-таблицы ORGS.

Источник истины по именам, адресам, каналам и числу чтений.
Доступ потребителей — только через атрибут модуля
(`from other import orgs_config` → `orgs_config.ORGS`), не `from … import
ORGS`: патч `other.orgs_config.ORGS` в тестах виден всем потребителям.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Org:
    name: str
    main_address: str  # "" = заглушка: не видна никому, кроме секретарей
    channels: tuple[str, ...]  # числовые chat_id строками (без префикса -100)
    readings: int  # 0 = одно чтение, один канал на любое


ORGS: tuple[Org, ...] = (
    Org(
        "PFM",
        "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        ("1863399780", "1652080456", "1649743884"),
        3,
    ),
    Org(
        "GORA",
        "GCVTXUMIUAENJH2XY4AOVGTJKPSCOXW3746PUH7QFGPBDOPPHYLIGORA",
        ("84131737",),
        3,  # один канал на 3 чтения
    ),
    Org(
        "USDMM",
        "GDHDC4GBNPMENZAOBB4NCQ25TGZPDRK6ZGWUGSI22TVFATOLRPSUUSDM",
        ("1789207509",),
        0,  # одно чтение; канал -1001789207509
    ),
    Org(
        "MTLA",
        "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        ("2042260878",),  # канал -1002042260878, Council Announcements
        3,
    ),
    Org(
        "TFM",
        "",
        (),
        0,  # TODO(владелец): адрес, канал, чтения
    ),
)

DEFAULT_ORG_NAME = "PFM"


def _validate(orgs: tuple[Org, ...]) -> None:
    """Целостность конфига; вызывается на импорте (битый конфиг = падение старта)."""
    seen: set[str] = set()
    for org in orgs:
        if not org.name:
            raise ValueError("orgs_config: имя организации не может быть пустым")
        if org.name in seen:
            raise ValueError(f"orgs_config: дубликат имени организации {org.name!r}")
        seen.add(org.name)
        if org.readings < 0:
            raise ValueError(
                f"orgs_config: {org.name}: readings не может быть отрицательным"
            )
        if org.main_address and not org.channels:
            raise ValueError(
                f"orgs_config: {org.name}: у организации с адресом должны быть каналы"
            )


_validate(ORGS)
