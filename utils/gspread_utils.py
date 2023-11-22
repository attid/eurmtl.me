import asyncio
import os
import gspread_asyncio
from google.oauth2.service_account import Credentials


def get_creds():
    # To obtain a service account JSON file, follow these steps:
    # https://gspread.readthedocs.io/en/latest/oauth2.html#for-bots-using-service-account
    key_path = os.path.join(os.path.dirname(__file__), 'mtl-google-doc.json')
    # print(start_path, key_path)

    creds = Credentials.from_service_account_file(key_path)
    scoped = creds.with_scopes([
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    return scoped


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


async def gs_get_last_id():
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")

    record = await ws.col_values(1)
    return int(record[-1]), len(record)


async def gs_save_new_decision(decision_id, short_name, url, username):
    last_number, last_col = await gs_get_last_id()
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    # 155	Обновление голосов  https://t.me/c/1649743884/243	@SomeoneAny
    await ws.update(values=[[decision_id, short_name, url, username]], range_name=f'A{last_col + 1}',
                    value_input_option='USER_ENTERED')
    # await ws.update(f'A{last_col + 1}', [[last_number + 1, datetime.now().strftime('%d.%m'), username, user_id, url,
    #                                      None, None, None, None, None, None, None, None, None, agent_username]],
    #                                      value_input_option='USER_ENTERED')


async def gs_get_decision(decision_id):
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    cell = await ws.find(str(decision_id), in_column=0)
    row_number = cell.row
    row_data = await ws.row_values(row_number)
    return row_data
    # ['155', 'Обновление голосов в мультиподписи МТЛ-фонда', 'https://t.me/c/1649743884/243', '@SomeoneAny', '', '', '', '02.10.23', '02.10.23']
    # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision


async def gs_update_decision(decision_id, col_id, value):
    # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision
    # 1     2       3       4       5       6       7       8       9
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    # 155	Обновление голосов  https://t.me/c/1649743884/243	@SomeoneAny
    cell = await ws.find(str(decision_id), in_column=0)
    await ws.update_cell(row=cell.row, col=col_id, value=value)


async def gs_get_asset(asset_code):
    agc = await agcm.authorize()
    ss = await agc.open("MTL_assets")
    ws = await ss.worksheet("ASSETS")
    cell = await ws.find(asset_code, in_column=0)
    if cell:
        row_number = cell.row
        row_data = await ws.row_values(row_number)
        if row_data[13] == 'TRUE':
            return row_data[5]
        # ['EURMTL', 'EURMTL', 'tokenized', 'F', '', 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V', 'mtl.montelibero.org', '45\xa0500', '1', '', 'https://t.me/eurmtl_club', '', '', 'TRUE', 'https://eurmtl.me/asset/EURMTL']
        # code	name	descr	status	stellar	issuer	domain	MTL-fund	e-rate	b-rate	chat	contract	person	eurmtl.me

if __name__ == "__main__":
    print(asyncio.run(gs_get_asset('EURMT')))
