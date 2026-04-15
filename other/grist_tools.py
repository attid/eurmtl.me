import asyncio
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from loguru import logger
from stellar_sdk import StrKey, ServerAsync
from stellar_sdk.client.aiohttp_client import AiohttpClient

from other.cache_tools import AsyncTTLCache
from other.telegram_tools import skynet_bot
from db.sql_models import User
from other.config_reader import config
from other.web_tools import HTTPSessionManager


@dataclass
class GristTableConfig:
    access_id: str
    table_name: str
    base_url: str = "https://montelibero.getgrist.com/api/docs"


# Enum для таблиц
@dataclass
class MTLGrist:
    NOTIFY_ACCOUNTS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Accounts")
    NOTIFY_ASSETS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Assets")
    NOTIFY_TREASURY = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Treasury")
    NOTIFY_MESSAGES = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Messages")

    MTLA_CHATS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_CHATS")
    MTLA_COUNCILS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_COUNCILS")

    SP_USERS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_USERS")
    SP_CHATS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_CHATS")
    QUESTIONS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "QUESTIONS")
    QUESTION_DATA = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "QUESTION_DATA")
    QUESTION_TEMPLATES = GristTableConfig(
        "3sFtdPU7Dcfw2XwTioLcJD", "QUESTION_TEMPLATES"
    )

    MAIN_CHAT_INCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_income")
    MAIN_CHAT_OUTCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_outcome")

    GRIST_access = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Access")
    GRIST_use_log = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Use_log")

    EURMTL_users = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Users")
    EURMTL_accounts = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Accounts")
    EURMTL_assets = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Assets")
    EURMTL_pools = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Pools")
    EURMTL_secretaries = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Secretaries")

    MTL_shareholders = GristTableConfig("cqmjqbs4e97hbKHyRADQ9N", "ShareHolders")
    MTL_admin_panel = GristTableConfig("cqmjqbs4e97hbKHyRADQ9N", "AdminPanel")


class GristAPI:
    def __init__(self, session_manager: HTTPSessionManager = None):
        self.session_manager = session_manager
        self.token = config.grist_token
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
        response = await self.session_manager.get_web_request(
            method="PUT", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
            case _:
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
        response = await self.session_manager.get_web_request(
            method="PATCH", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
            case _:
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
        response = await self.session_manager.get_web_request(
            method="POST", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
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
        user_record = grist_cache.find_by_index("EURMTL_users", telegram_id, "telegram_id")
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
