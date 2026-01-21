import pytest
from stellar_sdk import Keypair, Signer, SignerKey, Asset
from stellar_sdk.operation import (
    AccountMerge, SetOptions, Payment, AllowTrust, ManageData, Inflation, ChangeTrust, 
    PathPaymentStrictReceive, PathPaymentStrictSend, ManageSellOffer, ManageBuyOffer, 
    CreatePassiveSellOffer, BumpSequence
)

# Импортируем тестируемую функцию из вашего проекта
from services.stellar_client import get_operation_threshold_level

# --- Тестовые данные ---

# Операции с высоким порогом
@pytest.mark.parametrize("operation", [
    AccountMerge(destination=Keypair.random().public_key),
    SetOptions(signer=Signer(SignerKey.from_encoded_signer_key(Keypair.random().public_key), 1)),
    SetOptions(low_threshold=1, med_threshold=2, high_threshold=3),
])
def test_high_threshold_operations(operation):
    assert get_operation_threshold_level(operation) == 'high'

# Операции со средним порогом
@pytest.mark.parametrize("operation", [
    Payment(destination=Keypair.random().public_key, asset=Asset("USD", Keypair.random().public_key), amount="100"),
    ManageData(data_name="test", data_value="value"),
    ChangeTrust(asset=Asset("EUR", Keypair.random().public_key)),
    SetOptions(home_domain="eurmtl.me"), # SetOptions без изменения подписчиков/порогов
    PathPaymentStrictReceive(destination=Keypair.random().public_key, send_asset=Asset.native(), send_max="100", dest_asset=Asset("USD", Keypair.random().public_key), dest_amount="10", path=[]),
    ManageSellOffer(selling=Asset.native(), buying=Asset("USD", Keypair.random().public_key), amount="100", price="1.2"),
])
def test_medium_threshold_operations(operation):
    assert get_operation_threshold_level(operation) == 'med'

# Операции с низким порогом
@pytest.mark.parametrize("operation", [
    AllowTrust(trustor=Keypair.random().public_key, asset_code="USD", authorize=True),
    BumpSequence(bump_to=123456789)
])
def test_low_threshold_operations(operation):
    assert get_operation_threshold_level(operation) == 'low'

# Тест для неизвестной операции
def test_unknown_operation_defaults_to_high():
    # Создаем "фейковую" операцию, которой нет в SDK
    class UnknownOperation:
        pass

    unknown_op = UnknownOperation()
    
    # Просто проверяем, что возвращается 'high'
    assert get_operation_threshold_level(unknown_op) == 'high'
