# Использование Stellar URI через Telegram

## Назначение
Обмен Stellar транзакциями в формате URI через Telegram бота

## API Endpoints

### Добавление URI
`POST /remote/sep07/add`
- Параметры:
  - `uri`: Stellar URI (только TransactionStellarUri)
- Ответ:
```json
{
  "url": "https://t.me/MyMTLWalletBot?start=uri_abc123..."
}
```

### Получение URI
`GET /remote/sep07/get/{uuid}`
- Возвращает сохраненный URI

## Примеры

1. Добавление URI:
```python
import requests

response = requests.post(
    "https://example.com/remote/sep07/add",
    data={"uri": "web+stellar:tx?..."}
)
print(response.json()["url"])
```

2. Получение URI через бота:
```
/start uri_abc123...
```

