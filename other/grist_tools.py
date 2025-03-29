import asyncio
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from loguru import logger
from other.cache_tools import async_cache_with_ttl

from db.sql_models import User
from other.config_reader import config
from other.web_tools import HTTPSessionManager


@dataclass
class GristTableConfig:
    access_id: str
    table_name: str
    base_url: str = 'https://montelibero.getgrist.com/api/docs'


# Enum для таблиц
@dataclass
class MTLGrist:
    NOTIFY_ACCOUNTS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Accounts")
    NOTIFY_ASSETS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Assets")
    NOTIFY_TREASURY = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Treasury")

    MTLA_CHATS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_CHATS")
    MTLA_COUNCILS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_COUNCILS")

    SP_USERS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_USERS")
    SP_CHATS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_CHATS")

    MAIN_CHAT_INCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_income")
    MAIN_CHAT_OUTCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_outcome")

    GRIST_access = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Access")
    GRIST_use_log = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Use_log")

    EURMTL_users = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Users")
    EURMTL_accounts = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Accounts")
    EURMTL_assets = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Assets")
    EURMTL_pools = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Pools")
    EURMTL_secretaries = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Secretaries")


class GristAPI:
    def __init__(self, session_manager: HTTPSessionManager = None):
        self.session_manager = session_manager
        self.token = config.grist_token
        if not self.session_manager:
            self.session_manager = HTTPSessionManager()

    async def fetch_data(self, table: GristTableConfig, sort: Optional[str] = None,
                         filter_dict: Optional[Dict[str, List[Any]]] = None) -> List[Dict[str, Any]]:
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
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
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
        response = await self.session_manager.get_web_request(method='GET', url=url, headers=headers)

        match response.status:
            case 200 if response.data and "records" in response.data:
                return [{'id': record['id'], **record['fields']} for record in response.data["records"]]
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def put_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Обновляет данные в указанной таблице Grist.
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='PUT', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def patch_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Частично обновляет данные в указанной таблице Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для обновления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='PATCH', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def post_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Добавляет новые записи в указанную таблицу Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для добавления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='POST', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def load_table_data(self, table: GristTableConfig, sort: Optional[str] = None,
                              filter_dict: Optional[Dict[str, List[Any]]] = None) -> Optional[List[Dict[str, Any]]]:
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
            logger.warning(f"Ошибка при загрузке данных из таблицы {table.table_name}: {e}")
            return None


# Конфигурация
grist_session_manager = HTTPSessionManager()
grist_manager = GristAPI(grist_session_manager)
grist_cash = {} #todo: use ttl cache



@async_cache_with_ttl(ttl_seconds=36000)  # Кеш на 10 часов
async def get_secretaries() -> Dict[str, List[int]]:
    """
    Получает список секретарей из Grist и возвращает словарь:
    {
        account_id: [telegram_ids]  # список telegram_id секретарей для аккаунта
    }
    """
    secretaries = {}
    
    # Загружаем только необходимые данные
    secretary_records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_secretaries
    )
    
    if not secretary_records:
        return secretaries

    # Получаем account_id для всех записей
    account_records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_accounts,
        filter_dict={'id': [r['account'] for r in secretary_records if r.get('account')]}
    )
    account_id_map = {a['id']: a['account_id'] for a in account_records} if account_records else {}

    # Получаем telegram_id для всех пользователей
    all_user_ids = list({u for r in secretary_records for u in r.get('users', []) if isinstance(u, int)})
    user_records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_users,
        filter_dict={'id': all_user_ids}
    ) if all_user_ids else []
    user_telegram_map = {u['id']: u['telegram_id'] for u in user_records if u.get('telegram_id')} if user_records else {}

    # Формируем итоговую структуру
    for record in secretary_records:
        account_record_id = record.get('account')
        if not account_record_id or account_record_id not in account_id_map:
            continue
            
        account_id = account_id_map[account_record_id]
        telegram_ids = [
            user_telegram_map[user_id]
            for user_id in record.get('users', [])
            if user_id in user_telegram_map
        ]
        
        if telegram_ids:
            secretaries[account_id] = telegram_ids

    return secretaries


async def load_user_from_grist(account_id: Optional[str] = None, telegram_id: Optional[int] = None) -> Optional[User]:
    if account_id and account_id in grist_cash:
        return grist_cash[account_id]

    filter_dict = {}
    if account_id:
        filter_dict["account_id"] = [account_id]
    if telegram_id:
        filter_dict["telegram_id"] = [telegram_id]

    if not filter_dict:
        return None

    # eurmtl users
    user_records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_users,
        filter_dict=filter_dict
    )
    if user_records:
        user_record = user_records[0]
        user = User(telegram_id=user_record["telegram_id"], account_id=user_record["account_id"],
                    username=user_record["username"])
        if user.account_id:
            grist_cash[user.account_id] = user
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


if __name__ == '__main__':
    #asyncio.run(main())
    print(asyncio.run(get_secretaries()))
