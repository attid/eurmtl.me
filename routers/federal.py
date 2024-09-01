from quart import Blueprint, request, jsonify, make_response, render_template
from stellar_sdk import Network
from stellar_sdk.exceptions import BadRequestError
from stellar_sdk.sep.stellar_web_authentication import build_challenge_transaction

from config.config_reader import config
from db.sql_models import Addresses
from db.sql_pool import db_pool
from quart_cors import cors

blueprint = Blueprint('federal', __name__)
cors_enabled_blueprint = cors(blueprint, allow_origin="*")


@blueprint.route('/federation')
@blueprint.route('/federation/')
async def federation():
    # https://eurmtl.me/federation/?q=english*eurmtl.me&type=name
    # https://eurmtl.me/federation/?q=GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB&type=id
    if request.args.get('q') and request.args.get('type'):
        if request.args.get('type') == 'name':
            with db_pool() as db_session:
                address = db_session.query(Addresses).filter(Addresses.stellar_address == request.args.get('q')).first()
                if address:
                    result = {"stellar_address": address.stellar_address,
                              "account_id": address.account_id}
                    if address.memo:
                        result['memo_type'] = "text"
                        result['memo'] = address.memo
                    resp = jsonify(result)
                    resp.headers.add('Access-Control-Allow-Origin', '*')
                    return resp

        if request.args.get('type') == 'id':
            with db_pool() as db_session:
                address = db_session.query(Addresses).filter(Addresses.account_id == request.args.get('q')).first()
                if address:
                    result = {"stellar_address": address.stellar_address,
                              "account_id": address.account_id}
                    resp = jsonify(result)
                    resp.headers.add('Access-Control-Allow-Origin', '*')
                    return resp

    return jsonify({'error': "Not found."})


@blueprint.route('/.well-known/stellar.toml')
async def stellar_toml():
    resp = await make_response(await render_template('stellar.toml'))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Content-Type'] = 'text/plain'
    return resp


@blueprint.route('/sep6/info')
async def sep6_info():
    result = {
        "deposit": {
            "USDM": {
                "enabled": True,
                "authentication_required": False,
                "min_amount": 50,
                "max_amount": 3000,
                "fee_fixed": 2,
                "fee_percent": 0,
                "types": {
                    "TRC-20": {
                        "fields": {
                            "network": {
                                "description": "Choose your network",
                                "choices": ["TRC-20", "BEP-20"]
                            }
                        }
                    },
                    "BEP-20": {
                        "fields": {
                        }
                    }
                }
            },
            "EURMTL": {
                "enabled": True,
                "authentication_required": False,
                "min_amount": 50,
                "max_amount": 3000,
                "fee_fixed": 0,
                "fee_percent": 0,
                "types": {
                    "cash": {
                        "fields": {
                            "city": {
                                "description": "Choose your city",
                                "choices": ["Bar", "Budva", "Podgorica"]
                            },
                            "telegram": {
                                "description": "Your telegram username",
                                "optional": True
                            }
                        }
                    }
                }
            }
        },
        "withdraw": {
            "USDM": {
                "enabled": True,
                "authentication_required": False,
                "min_amount": 50,
                "max_amount": 3000,
                "fee_fixed": 2,
                "fee_percent": 0,
                "types": {
                    "TRC-20": {
                        "fields": {
                            "dest": {
                                "description": "The USDT address in TRC-20",
                                "optional": False
                            }
                        }
                    },
                    "BER-20": {
                        "fields": {
                            "dest": {
                                "description": "The USDT address in BEP-20",
                                "optional": False
                            }
                        }
                    },
                    "Stellar": {
                        "fields": {
                            "dest": {
                                "description": "The USDT address in Stellar network",
                                "optional": False
                            }
                        }
                    }

                }
            },
            "EURMTL": {
                "enabled": True,
                "authentication_required": False,
                "min_amount": 50,
                "max_amount": 3000,
                "fee_fixed": 0,
                "fee_percent": 0,
                "types": {
                    "Bar": {
                        "fields": {
                            "telegram": {
                                "description": "Your telegram username",
                                "optional": True
                            }
                        }
                    },
                    "Budva": {
                        "fields": {
                            "telegram": {
                                "description": "Your telegram username",
                                "optional": True
                            }
                        }
                    }
                }
            }
        },
        "fee": {
            "enabled": False
        },
        "deposit-exchange": {
            "enabled": False
        },
        "withdraw-exchange": {
            "enabled": False
        },
        "transactions": {
            "enabled": False
        },
        "transaction": {
            "enabled": False,
            "authentication_required": False
        },
        "features": {
            "account_creation": False,
            "claimable_balances": False
        }
    }
    resp = jsonify(result)
    # resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp


@blueprint.route('/sep6/deposit', methods=['GET', 'POST', 'OPTIONS'])
async def sep6_deposit():
    # /sep6/deposit?asset_code=USDM&account=GDXMB6I6RYYO7BIQNKNQ4XPY2RP5XJMBZEXVI5KFSG3PH3BRFAGQZXEP&claimable_balance_supported=false&type=undefined&amount=300
    asset_code = request.args.get('asset_code')
    account = request.args.get('account')
    type_ = request.args.get('type')
    amount = request.args.get('amount')
    result = {}
    if asset_code == 'USDM':
        result = {
            "how": "TJaGpx1zVVmKgYwSdeSr6YmsuDcHHhgZDS",
            "instructions": {
                "organization.crypto_address": {
                    "value": "TJaGpx1zVVmKgYwSdeSr6YmsuDcHHhgZDS",
                    "description": "TRC-20 address"
                }
            },
            "id": "0a35a1092b6cc705b2fe8130a2ea",
            "eta": 21600,
            "min_amount": 50,
            "max_amount": 3000,
            "fee_fixed": 0,
            "fee_percent": 0,
            "extra_info": {}
        }
    if asset_code == 'EURMTL':
        result = {
            "how": "Wait telegram message",
            "instructions": {
                "organization.website": {
                    "value": "eurmtl.me",
                    "description": "Wait telegram message"
                }
            },
            "id": "0a35a1092b6cc705b2fe8130a2ea",
            "eta": 21600,
            "min_amount": 50,
            "max_amount": 3000,
            "fee_fixed": 0,
            "fee_percent": 0,
            "extra_info": {}
        }

    resp = jsonify(result)
    # resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp


@blueprint.route('/sep6/withdraw', methods=['GET', 'POST', 'OPTIONS'])
async def sep6_withdraw():
    # /sep6/withdraw?asset_code=EURMTL&account=GDXMB6I6RYYO7BIQNKNQ4XPY2RP5XJMBZEXVI5KFSG3PH3BRFAGQZXEP&claimable_balance_supported=false&type=cash&dest=attid&city=Kislar
    asset_code = request.args.get('asset_code')
    account = request.args.get('account')
    type_ = request.args.get('type')
    amount = request.args.get('amount')
    result = {}
    if asset_code == 'USDM':
        result = {
            "account_id": "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI",
            "memo_type": "text",
            "memo": "89079dbc99bb3c554a48f21a7a14",
            "id": "89079dbc99bb3c554a48f21a7a14",
            "eta": 0,
            "min_amount": "30",
            "max_amount": "3000",
            "fee_fixed": 2,
            "fee_percent": 0,
            "extra_info": {
                "message": ""
            }
        }
    if asset_code == 'EURMTL':
        result = {
            "account_id": "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI",
            "memo_type": "text",
            "memo": "89079dbc99bb3c554a48f21a7a14",
            "id": "89079dbc99bb3c554a48f21a7a14",
            "eta": 0,
            "min_amount": "30",
            "max_amount": "3000",
            "fee_fixed": 2,
            "fee_percent": 0,
            "extra_info": {
                "message": ""
            }
        }

    resp = jsonify(result)
    # resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp


# https://anchor.mykobo.co/sep6/info
# https://sep6.whalestack.com/info
# https://sep6.whalestack.com/deposit?asset_code=LTC&account=GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI
# /sep6/deposit?asset_code=USDM&account=GDXMB6I6RYYO7BIQNKNQ4XPY2RP5XJMBZEXVI5KFSG3PH3BRFAGQZXEP&claimable_balance_supported=false&type=undefined&amount=300
# /sep6/withdraw?asset_code=EURMTL&account=GDXMB6I6RYYO7BIQNKNQ4XPY2RP5XJMBZEXVI5KFSG3PH3BRFAGQZXEP&claimable_balance_supported=false&type=cash&dest=attid&city=Kislar
# https://anchor.mtl.montelibero.org/sep6/transaction?id=0a35a1092b6cc705b2fe8130a2ea


@blueprint.route('/auth', methods=['GET', 'POST', 'OPTIONS'])
async def sep10_auth():
    # Обрабатываем только GET-запросы для аутентификации
    if request.method == 'GET':
        account = request.args.get('account')
        home_domain = request.args.get('home_domain')
        client_domain = request.args.get('client_domain')

        # Проверяем валидность запроса
        if not account or not home_domain:
            return jsonify({'error': 'Missing required parameters.'}), 400

        # Создаём вызов транзакции для аутентификации
        try:
            transaction = build_challenge_transaction(
                server_secret=config.signing_key.get_secret_value(),
                client_account_id=account,
                home_domain=home_domain,
                web_auth_domain='anchor.mtl.montelibero.org',
                client_domain=client_domain,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE
            )
        except BadRequestError as e:
            return jsonify({'error': str(e)}), 400

        # Возвращаем транзакцию клиенту
        return jsonify({'transaction': transaction})

    return jsonify({'error': 'Invalid request method.'}), 405
