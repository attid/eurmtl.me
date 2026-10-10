import asyncio
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import aiohttp
from loguru import logger
from stellar_sdk import StrKey, ServerAsync
from stellar_sdk.client.aiohttp_client import AiohttpClient
from pydantic import SecretStr

from other.cache_tools import AsyncTTLCache
from other.telegram_tools import skynet_bot
from db.sql_models import User
from other.config_reader import config
from other.web_tools import HTTPSessionManager


@dataclass
class GristTableConfig:
    access_id: str
    table_name: str
    base_url: str = "https://grist.eurmtl.me/api/docs"


# Аудит мутаций Grist: каждое изменение — одна строка в логе. Требование
# владельца (2026-10-10): «ни одного байта изменения в d2 не должно быть
# незамеченным». Шум сократим, когда всё отработает без ошибок.
_BRIEF_MAX = 120


def _brief(value: Any) -> Any:
    """Короткое представление значения поля для лога."""
    if isinstance(value, str) and len(value) > _BRIEF_MAX:
        return value[:_BRIEF_MAX] + f"…({len(value)} chars)"
    return value


def _recordsBrief(json_data: Dict[str, Any]) -> str:
    """records payload одной строкой: [{id: N, field: value, ...}, ...]."""
    records = json_data.get("records", []) if isinstance(json_data, dict) else []
    parts = []
    for record in records[:5]:  # больше 5 записей за раз d2 не пишет
        fields = record.get("fields", {})
        brief = {k: _brief(v) for k, v in fields.items()}
        row_id = record.get("id")
        prefix = f"id={row_id} " if row_id is not None else ""
        parts.append(f"[{prefix}{brief}]")
    if len(records) > 5:
        parts.append(f"…+{len(records) - 5} more")
    return " ".join(parts) if parts else str(json_data)[:_BRIEF_MAX]


def _log_mutation(method: str, table: GristTableConfig, json_data: Dict[str, Any]) -> None:
    logger.info(f"Grist {method} {table.table_name}: {_recordsBrief(json_data)}")


# Enum для таблиц
@dataclass
class MTLGrist:
    NOTIFY_ACCOUNTS = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Accounts")
    NOTIFY_ASSETS = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Assets")
    NOTIFY_TREASURY = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Treasury")
    NOTIFY_MESSAGES = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Messages")

    MTLA_CHATS = GristTableConfig("x4r7WiFKsJREzXS4vowwqj", "MTLA_CHATS")
    MTLA_COUNCILS = GristTableConfig("x4r7WiFKsJREzXS4vowwqj", "MTLA_COUNCILS")

    # SP_USERS/SP_CHATS — старый док (одноразовая миграция D1 их читает);
    # десижены с 2026-10-09 живут в eurmtlme-доке (решение владельца),
    # таблицы создаются автоматически при первом post_data.
    SP_USERS = GristTableConfig("hpZWKq729vw2D5AkG7oYYz", "SP_USERS")
    SP_CHATS = GristTableConfig("hpZWKq729vw2D5AkG7oYYz", "SP_CHATS")
    QUESTIONS = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "D2_QUESTIONS")
    QUESTION_DATA = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "D2_QUESTION_DATA")
    QUESTION_TEMPLATES = GristTableConfig(
        "3Fk4hjCv847GBx8ZTCPN2Y", "D2_QUESTION_TEMPLATES"
    )
    # Картинки d2-вопросов: FILE — attachment, схему/таблицу создаёт владелец
    # руками в UI (сайт никогда не создаёт схему Grist).
    D2_IMAGES = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "D2_IMAGES")

    MAIN_CHAT_INCOME = GristTableConfig("khWn5KMRbfUQQoaPydjhGt", "Main_chat_income")
    MAIN_CHAT_OUTCOME = GristTableConfig("khWn5KMRbfUQQoaPydjhGt", "Main_chat_outcome")

    GRIST_access = GristTableConfig("1sd6z3cHUPVQSgvyy7iARy", "Access")
    GRIST_use_log = GristTableConfig("1sd6z3cHUPVQSgvyy7iARy", "Use_log")

    EURMTL_users = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Users")
    EURMTL_accounts = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Accounts")
    EURMTL_assets = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Assets")
    EURMTL_pools = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Pools")
    EURMTL_secretaries = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Secretaries")

    MTL_shareholders = GristTableConfig("eNajcBuG4bFPzDvZfGC3JQ", "ShareHolders")
    MTL_admin_panel = GristTableConfig("eNajcBuG4bFPzDvZfGC3JQ", "AdminPanel")


class GristAPI:
    def __init__(
        self,
        session_manager: HTTPSessionManager = None,
        token: SecretStr | str | None = None,
    ):
        self.session_manager = session_manager
        configured_token = config.grist_token if token is None else token
        self.token = (
            configured_token.get_secret_value()
            if isinstance(configured_token, SecretStr)
            else configured_token
        )
        if not self.session_manager:
            self.session_manager = HTTPSessionManager()

    async def fetch_data(
        self,
        table: GristTableConfig,
        sort: Optional[str] = None,
        filter_dict: Optional[Dict[str, List[Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Загружает данные из указанной таблицы Grist.

        Args:
            table: Конфигурация таблицы
            sort: Параметр сортировки
            filter_dict: Словарь фильтрации в формате {"column": [value1, value2]}
                        Пример: {"TGID": [123456789]}
        """
        from urllib.parse import quote

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        params = []

        if sort:
            params.append(f"sort={sort}")
        if filter_dict:
            # Преобразуем словарь в JSON и кодируем для URL
            filter_json = json.dumps(filter_dict)
            encoded_filter = quote(filter_json)
            params.append(f"filter={encoded_filter}")

        if params:
            url = f"{url}?{'&'.join(params)}"
        response = await self.session_manager.get_web_request(
            method="GET", url=url, headers=headers
        )

        match response.status:
            case 200 if response.data and "records" in response.data:
                return [
                    {"id": record["id"], **record["fields"]}
                    for record in response.data["records"]
                ]
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def put_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Обновляет данные в указанной таблице Grist.
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        _log_mutation("PUT", table, json_data)
        response = await self.session_manager.get_web_request(
            method="PUT", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                logger.info(
                    f"Grist OK: PUT {table.table_name} {_recordsBrief(json_data)}"
                )
                return True
            case _:
                logger.error(
                    f"Grist FAIL: PUT {table.table_name} "
                    f"{_recordsBrief(json_data)} -> {response.status}"
                )
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def patch_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Частично обновляет данные в указанной таблице Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для обновления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        _log_mutation("PATCH", table, json_data)
        response = await self.session_manager.get_web_request(
            method="PATCH", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                logger.info(
                    f"Grist OK: PATCH {table.table_name} "
                    f"{_recordsBrief(json_data)}"
                )
                return True
            case _:
                logger.error(
                    f"Grist FAIL: PATCH {table.table_name} "
                    f"{_recordsBrief(json_data)} -> {response.status}"
                )
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def post_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Добавляет новые записи в указанную таблицу Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для добавления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        _log_mutation("POST", table, json_data)
        response = await self.session_manager.get_web_request(
            method="POST", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                logger.info(
                    f"Grist OK: POST {table.table_name} {_recordsBrief(json_data)}"
                )
                return True
            case _:
                logger.error(
                    f"Grist FAIL: POST {table.table_name} "
                    f"{_recordsBrief(json_data)} -> {response.status}"
                )
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def post_attachment(
        self,
        table: GristTableConfig,
        file_bytes: bytes,
        filename: str,
        fields: Dict[str, Any],
    ) -> int:
        """
        Загружает файл как Grist attachment и создаёт запись в таблице.

        1. POST /docs/{docId}/attachments (multipart/form-data) → {"id": N}.
        2. POST records в таблицу с fields {"FILE": attachment_id, ...};
           id созданной строки берём из ответа (Grist возвращает records).

        Args:
            table: Конфигурация таблицы (док + имя)
            file_bytes: Содержимое файла
            filename: Имя файла (для multipart)
            fields: Остальные поля записи (ORG, UPLOADED_BY, ...)

        Returns:
            row_id: id созданной записи в таблице.
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        attachments_url = f"{table.base_url}/{table.access_id}/attachments"
        form = aiohttp.FormData()
        form.add_field(
            "upload",
            file_bytes,
            filename=filename,
            content_type="application/octet-stream",
        )
        response = await self.session_manager.get_web_request(
            method="POST", url=attachments_url, headers=headers, data=form
        )
        match response.status:
            case 200 if isinstance(response.data, list) and response.data:
                attachment_id = response.data[0].get("id")
            case _:
                raise Exception(f"Ошибка загрузки attachment: Статус {response.status}")
        if attachment_id is None:
            raise Exception("Grist не вернул id attachment")

        records_url = (
            f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        )
        records_response = await self.session_manager.get_web_request(
            method="POST",
            url=records_url,
            headers=headers,
            json={"records": [{"fields": {"FILE": attachment_id, **fields}}]},
        )
        logger.info(
            f"Grist: attachment {attachment_id} ({filename}, "
            f"{len(file_bytes)}b) -> {table.table_name} {fields}"
        )
        match records_response.status:
            case 200 if isinstance(
                records_response.data, dict
            ) and records_response.data.get("records"):
                row_id = records_response.data["records"][0].get("id")
                if row_id is not None:
                    return int(row_id)
                raise Exception("Grist не вернул id созданной записи")
            case _:
                raise Exception(
                    f"Ошибка создания записи {table.table_name}: "
                    f"Статус {records_response.status}"
                )

    async def get_attachment(
        self, table: GristTableConfig, attachment_id: int
    ) -> bytes:
        """
        Скачивает содержимое attachment из дока.

        GET /docs/{docId}/attachments/{attachmentId} → bytes.

        Args:
            table: Конфигурация таблицы (используется access_id = docId)
            attachment_id: id attachment в доке

        Returns:
            Содержимое файла (bytes).
        """
        headers = {
            "accept": "application/octet-stream",
            "Authorization": f"Bearer {self.token}",
        }
        url = f"{table.base_url}/{table.access_id}/attachments/{attachment_id}/download"
        response = await self.session_manager.get_web_request(
            method="GET", url=url, headers=headers, return_type="bytes"
        )
        match response.status:
            case 200 if isinstance(response.data, bytes):
                return response.data
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def load_table_data(
        self,
        table: GristTableConfig,
        sort: Optional[str] = None,
        filter_dict: Optional[Dict[str, List[Any]]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Загружает данные из таблицы с обработкой ошибок.

        Args:
            table: Конфигурация таблицы
            sort: Параметр сортировки
            filter_dict: Словарь фильтрации в формате {"column": [value1, value2]}
                        Пример: {"TGID": [123456789]}
        """
        try:
            records = await self.fetch_data(table, sort, filter_dict)
            logger.info(f"Данные из таблицы {table.table_name} успешно загружены")
            return records
        except Exception as e:
            logger.warning(
                f"Ошибка при загрузке данных из таблицы {table.table_name}: {e}"
            )
            return None


MAX_NOTIFY_ERROR_LENGTH = 500


def extract_record_ids_from_grist_webhook(payload: Any) -> list[int]:
    if not isinstance(payload, list):
        return []

    record_ids: list[int] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        record_id = item.get("id")
        if record_id is None and isinstance(item.get("fields"), dict):
            record_id = item["fields"].get("id")
        try:
            if record_id is not None:
                record_ids.append(int(record_id))
        except (TypeError, ValueError):
            continue
    return record_ids


async def load_notify_message_records_by_ids(record_ids: list[int]) -> list[dict]:
    records = await grist_manager.load_table_data(MTLGrist.NOTIFY_MESSAGES)
    if not records:
        return []
    wanted_ids = set(record_ids)
    return [record for record in records if int(record.get("id", 0)) in wanted_ids]


def should_send_notify_message_record(record: dict) -> bool:
    if not str(record.get("messsage") or "").strip():
        return False
    if record.get("send_date"):
        return False
    if str(record.get("error_message") or "").strip():
        return False
    return True


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, "", 0, 0.0, "0"):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized or None


async def patch_notify_message_record(record_id: int, fields: dict[str, Any]) -> bool:
    return await grist_manager.patch_data(
        MTLGrist.NOTIFY_MESSAGES,
        {"records": [{"id": record_id, "fields": fields}]},
    )


def _truncate_notify_error(error_text: str) -> str:
    if len(error_text) <= MAX_NOTIFY_ERROR_LENGTH:
        return error_text
    return error_text[: MAX_NOTIFY_ERROR_LENGTH - 3] + "..."


async def send_notify_message_record(record: dict) -> dict[str, Any]:
    record_id = int(record["id"])
    if not should_send_notify_message_record(record):
        return {"status": "skipped", "id": record_id}

    reply_to_message_id = _normalize_optional_int(record.get("reply_to"))
    message_thread_id = _normalize_optional_int(record.get("topik_id"))

    send_kwargs = {
        "chat_id": record["chat_id"],
        "text": record["messsage"],
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    if reply_to_message_id is not None:
        send_kwargs["reply_to_message_id"] = reply_to_message_id
    if message_thread_id is not None:
        send_kwargs["message_thread_id"] = message_thread_id

    try:
        await skynet_bot.send_message(**send_kwargs)
    except Exception as exc:
        error_text = _truncate_notify_error(str(exc))
        await patch_notify_message_record(record_id, {"error_message": error_text})
        return {"status": "failed", "id": record_id, "error": error_text}

    await patch_notify_message_record(
        record_id,
        {"send_date": int(datetime.now(timezone.utc).timestamp()), "error_message": ""},
    )
    return {"status": "sent", "id": record_id}


async def update_mtl_shareholders_balance():
    """
    Обновляет балансы MTL и MTLRECT для всех акционеров в таблице MTL_shareholders.
    """
    logger.info("Запуск обновления балансов акционеров MTL.")
    try:
        shareholders = await grist_manager.load_table_data(MTLGrist.MTL_shareholders)
        if not shareholders:
            logger.info("В таблице MTL_shareholders не найдено акционеров.")
            return

        updates = []
        async with ServerAsync(
            "https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            for shareholder in shareholders:
                stellar_address = shareholder.get("stellar")
                current_balance = shareholder.get("MTL") or 0
                new_balance = 0

                if stellar_address and StrKey.is_valid_ed25519_public_key(
                    stellar_address
                ):
                    try:
                        # Используем server.accounts() для получения данных об аккаунте
                        account_details = (
                            await server.accounts().account_id(stellar_address).call()
                        )
                        balances = account_details.get("balances", [])

                        mtl_balance = 0.0
                        mtlrect_balance = 0.0
                        for balance in balances:
                            if balance.get("asset_code") == "MTL":
                                mtl_balance = float(balance.get("balance", 0.0))
                            elif balance.get("asset_code") == "MTLRECT":
                                mtlrect_balance = float(balance.get("balance", 0.0))

                        new_balance = round(mtl_balance + mtlrect_balance, 2)

                    except Exception as e:
                        # Обработка случаев, когда аккаунт не найден (например, 404)
                        logger.warning(
                            f"Не удалось получить данные для {stellar_address}: {e}"
                        )
                        new_balance = 0

                if current_balance != new_balance:
                    updates.append(
                        {"id": shareholder["id"], "fields": {"MTL": new_balance}}
                    )

        if updates:
            logger.info(f"Найдено {len(updates)} акционеров для обновления.")
            update_data = {"records": updates}
            await grist_manager.patch_data(MTLGrist.MTL_shareholders, update_data)
            logger.info("Балансы акционеров MTL успешно обновлены.")
        else:
            logger.info("Обновление балансов акционеров MTL не требуется.")

    except Exception as e:
        logger.error(f"Произошла ошибка при обновлении балансов акционеров MTL: {e}")


# Конфигурация
grist_session_manager = HTTPSessionManager()
grist_manager = GristAPI(grist_session_manager)

# Канал фонда по умолчанию (fallback, если организация не найдена в конфиге).
# Прод: (0, 1863399780, 1652080456, 1649743884); тест: (0, 1837984392, ...).
DEFAULT_FUND_CHAT_IDS = (0, 1863399780, 1652080456, 1649743884)
DEFAULT_FUND_TEST_CHAT_IDS = (0, 1837984392, 1837984392, 1837984392)
# Реэкспорт из orgs_config: существующие импорты (decision.py) не ломаются.
from other.orgs_config import DEFAULT_ORG_NAME as DEFAULT_ORG_NAME  # noqa: E402


def _fallback_fund_channel(reading: int) -> str | None:
    from other.config_reader import config

    chat_ids = DEFAULT_FUND_TEST_CHAT_IDS if config.test_mode else DEFAULT_FUND_CHAT_IDS
    if reading <= 0 or reading >= len(chat_ids):
        return None
    return str(chat_ids[reading])


def resolve_org_channel(org_name: str | None, reading: int) -> str | None:
    """Канал публикации: чтение N организации из orgs_config.ORGS.

    readings>0: чтение N идёт в channels[min(N, len)-1] (нумерация чтений с 1).
    readings=0: у организации один канал — любой запрос уходит в channels[0].
    Нет организации: fallback на хардкод фонда; вне 1..3 — None.
    Возвращает числовой chat_id строкой (без префикса -100) или None.
    """
    from other import orgs_config

    org = None
    if org_name:
        org = next(
            (o for o in orgs_config.ORGS if (o.name or "") == org_name),
            None,
        )
    if org is None:
        return _fallback_fund_channel(reading)

    channels = org.channels
    if not channels:
        return None
    readings = int(org.readings)
    if readings <= 0:
        return channels[0]
    if reading <= 0:
        return None
    return channels[min(reading, len(channels)) - 1]


grist_cash = AsyncTTLCache(
    ttl_seconds=86400
)  # Кеш для найденных пользователей на 24 часа
not_found_cache = AsyncTTLCache(
    ttl_seconds=3600
)  # Кеш для ненайденных пользователей на 1 час
assets_cache = AsyncTTLCache(ttl_seconds=86400)  # Кеш для найденных активов на 24 часа
assets_not_found_cache = AsyncTTLCache(
    ttl_seconds=3600
)  # Кеш для ненайденных активов на 1 час

org_signers_cache = AsyncTTLCache(
    ttl_seconds=300
)  # Подписанты MAIN_ADDRESS организаций на 5 минут

HORIZON_URL = "https://horizon.stellar.org"


async def _org_main_address_signers(main_address: str) -> list[str]:
    """Публичные ключи подписантов счёта организации через Horizon.

    Ошибка сети/счёта — пустой список (организация просто не видна).
    """
    from other.web_tools import http_session_manager

    try:
        response = await http_session_manager.get_web_request(
            "GET",
            f"{HORIZON_URL}/accounts/{main_address}",
            return_type="json",
        )
    except Exception as e:
        logger.warning(f"Error loading signers for {main_address}: {e}")
        return []
    if response.status != 200:
        logger.warning(f"Horizon returned {response.status} for {main_address} signers")
        return []
    signers = (response.data or {}).get("signers", [])
    return [
        signer["key"]
        for signer in signers
        if signer.get("key") and int(signer.get("weight", 0)) > 0
    ]


async def load_org_signers(main_addresses: List[str]) -> Dict[str, set]:
    """Подписанты нескольких MAIN_ADDRESS; Horizon дергается параллельно."""
    unique_addresses = list(dict.fromkeys(addr for addr in main_addresses if addr))
    signer_lists = await asyncio.gather(
        *(_org_main_address_signers(addr) for addr in unique_addresses)
    )
    return dict(zip(unique_addresses, signer_lists))


async def user_org_names(user_telegram_id: int) -> set:
    """Имена организаций, видимых пользователю: он подписант MAIN_ADDRESS.

    Тест-режим: Horizon не дергается — подписанты берутся из grist_cache
    (EURMTL_users/account_id), как для прода, только источник счётов другой.
    activate_stand мокает stellar_client.get_fund_signers; здесь свой путь.
    """
    from other import orgs_config

    cache_key = f"org_names:{user_telegram_id}"
    cached = await org_signers_cache.get(cache_key)
    if cached is not None:
        return cached

    org_addresses = {o.name: o.main_address for o in orgs_config.ORGS if o.main_address}

    if config.test_mode:
        # Стенд: вместо Horizon — таблицы двойника. Подписант счёта =
        # пользователь, чей account_id совпадает с MAIN_ADDRESS.
        signers_by_address: Dict[str, set] = {}
        for address in org_addresses.values():
            if not address:
                continue
            signers_by_address[address] = {address}
        users_map = {}
        for address in signers_by_address:
            account_user = await grist_cash.get(address)
            if account_user is not None:
                users_map[address] = account_user
        if not users_map:
            from other.grist_cache import grist_cache

            for address in signers_by_address:
                user_record = grist_cache.find_by_index("EURMTL_users", address)
                if user_record:
                    users_map[address] = User(
                        telegram_id=user_record["telegram_id"],
                        account_id=user_record["account_id"],
                        username=user_record.get("username"),
                    )
    else:
        signers_by_address = await load_org_signers(list(org_addresses.values()))

        signer_account_ids = {
            signer_key
            for signer_keys in signers_by_address.values()
            for signer_key in signer_keys
        }
        users_map = await load_users_from_grist(list(signer_account_ids))

    visible: set = set()
    for org_name, address in org_addresses.items():
        if not address:
            continue
        for signer_key in signers_by_address.get(address, []):
            user = users_map.get(signer_key)
            if (
                user
                and user.telegram_id
                and int(user.telegram_id) == int(user_telegram_id)
            ):
                visible.add(org_name)
                break

    await org_signers_cache.set(cache_key, visible)
    return visible


async def get_grist_asset_by_code(asset_code: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные об активе из кеша по его коду.
    Проверяет что у актива включен QR (need_QR = True).
    """
    from other.grist_cache import grist_cache

    # Ищем в кеше по индексу
    asset_data = grist_cache.find_by_index("EURMTL_assets", asset_code)

    # Проверяем что у актива включен QR
    if asset_data and asset_data.get("need_QR") is True:
        return asset_data

    return None


async def get_secretaries() -> Dict[str, List[int]]:
    """
    Получает список секретарей из кеша и возвращает словарь:
    {
        account_id: [telegram_ids]  # список telegram_id секретарей для аккаунта
    }
    """
    from other.grist_cache import grist_cache

    secretaries = {}

    # Получаем все данные из кеша
    secretary_records = grist_cache.get_table_data("EURMTL_secretaries")
    account_records = grist_cache.get_table_data("EURMTL_accounts")
    user_records = grist_cache.get_table_data("EURMTL_users")

    if not secretary_records:
        return secretaries

    # Создаем маппинги из кешированных данных
    account_id_map = {
        a["id"]: a["account_id"]
        for a in account_records
        if a.get("id") and a.get("account_id")
    }
    user_telegram_map = {
        u["id"]: u["telegram_id"]
        for u in user_records
        if u.get("id") and u.get("telegram_id")
    }

    # Формируем итоговую структуру
    for record in secretary_records:
        account_record_id = record.get("account")
        if not account_record_id or account_record_id not in account_id_map:
            continue

        account_id = account_id_map[account_record_id]
        telegram_ids = [
            user_telegram_map[user_id]
            for user_id in record.get("users", [])
            if user_id in user_telegram_map
        ]

        if telegram_ids:
            secretaries[account_id] = telegram_ids

    return secretaries


async def load_user_from_grist(
    account_id: Optional[str] = None, telegram_id: Optional[int] = None
) -> Optional[User]:
    if account_id:
        cached_user = await grist_cash.get(account_id)
        if cached_user:
            return cached_user

    # Используем новый кеш
    from other.grist_cache import grist_cache

    if account_id:
        # Ищем по индексу account_id
        user_record = grist_cache.find_by_index("EURMTL_users", account_id)
    elif telegram_id:
        # Ищем по дополнительному индексу telegram_id
        user_record = grist_cache.find_by_index(
            "EURMTL_users", telegram_id, "telegram_id"
        )
    else:
        return None

    if user_record:
        user = User(
            telegram_id=user_record["telegram_id"],
            account_id=user_record["account_id"],
            username=user_record["username"],
        )
        if user.account_id:
            await grist_cash.set(user.account_id, user)
        return user

    return None


async def main():
    # Пример загрузки данных
    assets = await grist_manager.load_table_data(MTLGrist.EURMTL_pools)
    if assets:
        print(json.dumps(assets, indent=2))
    await grist_session_manager.close()

    # Пример обновления данных
    # update_data = {"records": [{"fields": {"name": "New Asset", "value": 100}}]}
    # success = await grist_notify.put_data('Assets', update_data)
    # if success:
    #     logger.info("Данные успешно обновлены")


async def load_users_from_grist(account_ids: List[str]) -> Dict[str, User]:
    """
    Загружает пользователей из кеша по списку account_id и возвращает словарь.
    """
    if not account_ids:
        return {}

    # 1. Проверяем старый кеш для совместимости
    cached_users = {}
    get_tasks = [asyncio.create_task(grist_cash.get(acc_id)) for acc_id in account_ids]
    results = await asyncio.gather(*get_tasks)
    for acc_id, user in zip(account_ids, results):
        if user:
            cached_users[acc_id] = user

    # Определяем ID, которые нужно искать дальше
    ids_to_check = [acc_id for acc_id in account_ids if acc_id not in cached_users]

    if not ids_to_check:
        return cached_users

    # 2. Используем новый кеш для оставшихся ID
    from other.grist_cache import grist_cache

    found_users_map = {}
    for acc_id in ids_to_check:
        user_record = grist_cache.find_by_index("EURMTL_users", acc_id)
        if user_record:
            user = User(
                telegram_id=user_record["telegram_id"],
                account_id=user_record["account_id"],
                username=user_record["username"],
            )
            if user.account_id:
                await grist_cash.set(
                    user.account_id, user
                )  # Добавляем в старый кеш для совместимости
                found_users_map[user.account_id] = user

    # 3. Собираем итоговый результат
    return {**cached_users, **found_users_map}


if __name__ == "__main__":
    # asyncio.run(main())
    print(asyncio.run(update_mtl_shareholders_balance()))
