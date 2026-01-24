import asyncio
from datetime import datetime, timezone
from dateutil.parser import parse
from quart import Blueprint, render_template
from stellar_sdk import Server, Asset

blueprint = Blueprint('cup', __name__)


def decode_asset(asset):
    arr = asset.split('-')
    if arr[0] == 'XLM':
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


@blueprint.route('/cup/<asset1>/<asset2>')
@blueprint.route('/cup/orderbook/<asset1>/<asset2>')
async def cmd_orderbook(asset1, asset2):
    asset1, asset2 = decode_asset(asset1), decode_asset(asset2)
    orders = {
        'sellers': [],
        'buyers': []
    }
    need_round = 7
    try:
        server = Server(horizon_url="https://horizon.stellar.org")

        sellers_offers = server.offers().for_selling(asset1).for_buying(asset2).limit(200).call()
        buyers_offers = server.offers().for_buying(asset1).for_selling(asset2).limit(200).call()

        sellers_offers['_embedded']['records'] = sorted(sellers_offers['_embedded']['records'],
                                                        key=lambda x: float(x['price']), reverse=True)
        buyers_offers['_embedded']['records'] = sorted(buyers_offers['_embedded']['records'],
                                                       key=lambda x: float(x['price']), reverse=False)

        if float(sellers_offers['_embedded']['records'][-1]['price']) > 1:
            need_round = 3

        for offer in sellers_offers['_embedded']['records']:
            price_rounded = round(float(offer['price']), need_round)
            if price_rounded == 0 or round(float(offer['amount']), need_round) == 0:
                continue

            # Поиск существующего заказа с округленной ценой
            existing_order = next((order for order in orders['sellers'] if order['price'] == price_rounded), None)

            if existing_order:
                # Если заказ с такой ценой существует, добавляем к нему количество
                existing_order['amount'] += round(float(offer['amount']), need_round)
                existing_order['total'] += round(float(offer['amount']) * price_rounded, need_round)
            else:
                # Иначе добавляем новый заказ
                order_info = {
                    'amount': round(float(offer['amount']), need_round),
                    'price': price_rounded,
                    'total': round(float(offer['amount']) * price_rounded, need_round)
                }
                orders['sellers'].append(order_info)

        # Сортировка списка продаж по цене
        orders['sellers'] = sorted(orders['sellers'], key=lambda x: x['price'], reverse=True)

        # Обработка предложений для sell_2_buy_1_offers
        for offer in buyers_offers['_embedded']['records']:
            price_rounded = round(1 / float(offer['price']), need_round)
            if price_rounded == 0 or round(float(offer['amount']), need_round) == 0:
                continue

            # Поиск существующего заказа с округленной ценой
            existing_order = next((order for order in orders['buyers'] if order['price'] == price_rounded), None)

            if existing_order:
                # Если заказ с такой ценой существует, добавляем к нему количество
                existing_order['amount'] += round(float(offer['amount']), need_round)
                existing_order['total'] += round(float(offer['amount']) * price_rounded, need_round)
            else:
                # Иначе добавляем новый заказ
                order_info = {
                    'amount': round(float(offer['amount']) / price_rounded, need_round),
                    'price': price_rounded,
                    'total': round(float(offer['amount']), need_round)
                }
                orders['buyers'].append(order_info)

        # Сортировка списка покупок по убыванию цены (так как это список покупок)
        orders['buyers'] = sorted(orders['buyers'], key=lambda x: x['price'], reverse=True)
    except Exception as e:
        print(e)
        pass

    lowest_sell_price = min(order['price'] for order in orders['sellers']) if orders['sellers'] else 1
    highest_buy_price = max(order['price'] for order in orders['buyers']) if orders['buyers'] else 1

    spread_amount = round(lowest_sell_price - highest_buy_price, need_round)
    spread_percentage = round((spread_amount / lowest_sell_price) * 100, 2)

    # Теперь передаем все необходимые данные в шаблон:
    # asset_url = f'{asset1.code}-{asset1.issuer}/{asset2.code}-{asset2.issuer}'
    asset_url = f'{asset1.code}-{asset1.issuer}' if asset1.issuer else f'{asset1.code}'
    asset_url = f'{asset_url}/{asset2.code}-{asset2.issuer}' if asset2.issuer else f'{asset_url}/{asset2.code}'
    resp = await render_template('cup.orderbook.html', orders=orders, spread_amount=spread_amount,
                                 spread_percentage=spread_percentage, assets=[asset1, asset2], asset_url=asset_url,
                                 scopuly_url=get_scopuly_url(asset1, asset2), active_page='orderbook')
    return resp


@blueprint.route('/cup/trades/<asset1>/<asset2>')
async def cmd_trades(asset1, asset2):
    asset1, asset2 = decode_asset(asset1), decode_asset(asset2)
    try:
        server = Server(horizon_url="https://horizon.stellar.org")
        trades_resp = server.trades().for_asset_pair(asset1, asset2).limit(200).order(desc=True).call()
        trades = trades_resp['_embedded']['records']

        results = []
        for trade in trades:
            # Рассчитываем цену
            price = float(trade['price']['n']) / float(trade['price']['d'])

            # Получаем сумму
            amount = float(trade['base_amount'])  # или trade['counter_amount']

            # Рассчитываем, сколько минут прошло с момента закрытия сделки
            close_time = parse(trade['ledger_close_time'])
            now = datetime.now(timezone.utc)
            minutes_ago = (now - close_time).total_seconds() / 60

            results.append({
                "price": round(price, 3),
                "amount": amount,
                "minutes_ago": round(minutes_ago)
            })

        # Здесь вы можете возвращать результаты, сохранять их или делать что-то еще
        if results:
            for i in range(0, len(results) - 1):
                results[i]['up'] = results[i]['price'] > results[i + 1]['price']

            results[len(results) - 1]['up'] = False

        asset_url = f'{asset1.code}-{asset1.issuer}/{asset2.code}-{asset2.issuer}'
        resp = await render_template('cup.trades.html', trades=results,
                                     assets=[asset1, asset2], asset_url=asset_url,
                                     active_page='trades')

        return resp
    except Exception as e:
        print(e)
        pass


@blueprint.route('/cup/chart/<asset1>/<asset2>')
async def cmd_chart(asset1, asset2):
    asset1, asset2 = decode_asset(asset1), decode_asset(asset2)
    orders = {
        'sellers': [],
        'buyers': []
    }
    try:
        server = Server(horizon_url="https://horizon.stellar.org")

        sellers_offers = server.offers().for_selling(asset1).for_buying(asset2).limit(200).call()
        buyers_offers = server.offers().for_buying(asset1).for_selling(asset2).limit(200).call()

        for offer in sellers_offers['_embedded']['records']:
            price_rounded = round(float(offer['price']), 3)
            if price_rounded == 0 or round(float(offer['amount']), 3) == 0:
                continue

            # Поиск существующего заказа с округленной ценой
            existing_order = next((order for order in orders['sellers'] if order['price'] == price_rounded), None)

            if existing_order:
                # Если заказ с такой ценой существует, добавляем к нему количество
                existing_order['amount'] += round(float(offer['amount']), 3)
                existing_order['total'] += round(float(offer['amount']) * price_rounded, 3)
            else:
                # Иначе добавляем новый заказ
                order_info = {
                    'amount': round(float(offer['amount']), 3),
                    'price': price_rounded,
                    'total': round(float(offer['amount']) * price_rounded, 3)
                }
                orders['sellers'].append(order_info)

        # Сортировка списка продаж по цене
        orders['sellers'] = sorted(orders['sellers'], key=lambda x: x['price'], reverse=True)

        # Обработка предложений для sell_2_buy_1_offers
        for offer in buyers_offers['_embedded']['records']:
            price_rounded = round(1 / float(offer['price']), 3)
            if price_rounded == 0 or round(float(offer['amount']), 3) == 0:
                continue

            # Поиск существующего заказа с округленной ценой
            existing_order = next((order for order in orders['buyers'] if order['price'] == price_rounded), None)

            if existing_order:
                # Если заказ с такой ценой существует, добавляем к нему количество
                existing_order['amount'] += round(float(offer['amount']), 3)
                existing_order['total'] += round(float(offer['amount']) * price_rounded, 3)
            else:
                # Иначе добавляем новый заказ
                order_info = {
                    'amount': round(float(offer['amount']) / price_rounded, 3),
                    'price': price_rounded,
                    'total': round(float(offer['amount']), 3)
                }
                orders['buyers'].append(order_info)

        # Сортировка списка покупок по убыванию цены (так как это список покупок)
        orders['buyers'] = sorted(orders['buyers'], key=lambda x: x['price'], reverse=True)
    except Exception as e:
        print(e)
        pass

    max_sellers_amount = max(orders['sellers'], key=lambda x: x['amount'])['amount'] if orders['sellers'] else 0
    max_buyers_amount = max(orders['buyers'], key=lambda x: x['amount'])['amount'] if orders['buyers'] else 0
    max_amount = max(max_sellers_amount, max_buyers_amount)

    for order in orders['sellers']:
        order['percent'] = (order['amount'] / max_amount) * 100

    for order in orders['buyers']:
        order['percent'] = (order['amount'] / max_amount) * 100

    # Теперь передаем все необходимые данные в шаблон:
    asset_url = f'{asset1.code}-{asset1.issuer}/{asset2.code}-{asset2.issuer}'
    resp = await render_template('cup.chart.html', orders=orders,
                                 assets=[asset1, asset2], asset_url=asset_url)
    return resp


def get_send_swap_cost(asset1, asset2, amount):
    server = Server(horizon_url="https://horizon.stellar.org")
    swap_list = server.strict_send_paths(asset1, amount, [asset2]).limit(200).call()
    if swap_list['_embedded']['records']:
        return swap_list['_embedded']['records'][0]['destination_amount']
    else:
        return 0


def get_receive_swap_cost(asset1, asset2, amount):
    server = Server(horizon_url="https://horizon.stellar.org")
    swap_list = server.strict_receive_paths([asset1], asset2, amount).limit(200).call()
    if swap_list['_embedded']['records']:
        return swap_list['_embedded']['records'][-1]['source_amount']
    else:
        return 0


@blueprint.route('/cup/swap/<asset1>/<asset2>')
async def cmd_swap_book(asset1, asset2):
    asset1, asset2 = decode_asset(asset1), decode_asset(asset2)
    cost_list = ('10000', '1000', '100', '10', '1')

    orders = {
        'sellers': [],
        'buyers': []
    }
    need_round = 7
    try:
        # if float(sellers_offers['_embedded']['records'][-1]['price']) > 1:
        need_round = 3
        for cost in cost_list:
            swap_cost = get_send_swap_cost(asset1, asset2, cost)

            order_info = {
                'amount': round(float(cost), need_round),
                'price': round(float(cost) / float(swap_cost), need_round),
                'total': round(float(swap_cost), need_round)
            }
            orders['sellers'].append(order_info)

        for cost in reversed(cost_list):
            swap_cost = get_receive_swap_cost(asset2, asset1, cost)

            order_info = {
                'amount': round(float(cost), need_round),
                'price': round(float(cost) / float(swap_cost), need_round),
                'total': round(float(swap_cost), need_round)
            }
            orders['buyers'].append(order_info)

    except Exception as e:
        print(e)
        pass

    lowest_sell_price = min(order['price'] for order in orders['sellers']) if orders['sellers'] else 1
    highest_buy_price = max(order['price'] for order in orders['buyers']) if orders['buyers'] else 1

    spread_amount = round(lowest_sell_price - highest_buy_price, need_round)
    spread_percentage = round((spread_amount / lowest_sell_price) * 100, 2)

    # Теперь передаем все необходимые данные в шаблон:
    # asset_url = f'{asset1.code}-{asset1.issuer}/{asset2.code}-{asset2.issuer}'
    asset_url = f'{asset1.code}-{asset1.issuer}' if asset1.issuer else f'{asset1.code}'
    asset_url = f'{asset_url}/{asset2.code}-{asset2.issuer}' if asset2.issuer else f'{asset_url}/{asset2.code}'
    resp = await render_template('cup.swap.html', orders=orders, spread_amount=spread_amount,
                                 spread_percentage=spread_percentage, assets=[asset1, asset2], asset_url=asset_url,
                                 active_page='swap', scopuly_url=get_scopuly_url(asset1, asset2))
    return resp


def get_scopuly_url(asset1, asset2):
    # Base URL for the Scopuly trade link
    base_url = "https://scopuly.com/trade"

    def get_issuer(asset):
        # Special handling for native asset (XLM)
        if asset.code == "XLM":
            return "native"
        else:
            return asset.issuer

    # Construct and return the full URL
    return f"{base_url}/{asset1.code}-{asset2.code}/{get_issuer(asset1)}/{get_issuer(asset2)}"


if __name__ == '__main__':
    asyncio.run(cmd_swap_book('EURMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V',
                              'USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN'))
    pass
