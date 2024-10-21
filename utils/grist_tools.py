import asyncio
import aiohttp
from loguru import logger

from config.config_reader import config

grist_notify = "https://montelibero.getgrist.com/api/docs/oNYTdHkEstf9X7dkh7yH11"
grist_main_chat_info = "https://montelibero.getgrist.com/api/docs/gnXfashifjtdExQoeQeij6"

async def get_web_request(method, url, json=None, headers=None, data=None, return_type=None):
    async with aiohttp.ClientSession() as web_session:
        if method.upper() == 'POST':
            request_coroutine = web_session.post(url, json=json, headers=headers, data=data)
        elif method.upper() == 'GET':
            request_coroutine = web_session.get(url, headers=headers, params=data)
        elif method.upper() == 'PUT':
            request_coroutine = web_session.put(url, json=json, headers=headers)
        else:
            raise ValueError("Неизвестный метод запроса")

        async with request_coroutine as response:
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type or return_type == 'json':
                return response.status, await response.json()
            else:
                return response.status, await response.text()


async def fetch_grist_data(grist, table_name):
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {config.grist_token}'
    }
    url = f'{grist}/tables/{table_name}/records'
    status, response = await get_web_request('GET', url, headers=headers)
    if status == 200 and response and "records" in response:
        return [record['fields'] for record in response["records"]]
    else:
        raise Exception(f'Ошибка запроса: Статус {status}')

async def put_grist_data(grist, table_name, json_data):
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {config.grist_token}'
    }
    url = f'{grist}/tables/{table_name}/records'
    status, response = await get_web_request('PUT', url, headers=headers, json=json_data)
    if status == 200:
        return True
    else:
        raise Exception(f'Ошибка запроса: Статус {status}')

async def load_notify_info_accounts():
    try:
        records = await fetch_grist_data(grist_notify, 'Accounts')
        return records
    except Exception as e:
        logger.warning(f"Ошибка при загрузке данных accounts: {e}")

async def load_notify_info_assets():
    try:
        records = await fetch_grist_data(grist_notify, 'Assets')
        return records
    except Exception as e:
        logger.warning(f"Ошибка при загрузке данных assets: {e}")


if __name__ == '__main__':
    _ = asyncio.run(load_notify_info_assets())
    print(_)
