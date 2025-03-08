# SEP-7 Test API

## Описание
API для тестирования SEP-7 аутентификации через Stellar. Позволяет инициировать процесс аутентификации и проверять его статус.

## Endpoints

### POST /remote/sep07/auth/init
Инициализация процесса аутентификации.

#### Запрос
```json
{
  "domain": "example.com",  // домен сайта
  "nonce": "abc123",         // уникальный идентификатор сессии рекомендуемый  token_hex(8)
  "salt": "salt"         // соль token_hex(4) не обязательный параметр
}
```

#### Ответ
```json
{
  "qr_path": "/static/qr/uuid.png",  // путь к QR-коду
  "uri": "web+stellar:tx?xdr=...",   // SEP-7 URI для подписи
  "status_url": "https://eurmtl.me/remote/sep07/auth/status/abc123/salt"  // URL для проверки статуса
}
```

### GET /remote/sep07/auth/status/{nonce}/{salt}
Проверка статуса аутентификации. Если соль не совпадает с сохраненной, возвращается ошибка "nonce not found".

#### Ответ (в процессе)
```json
{
  "authenticated": false,
  "nonce": "abc123"
}
```

#### Ответ (успех)
```json
{
  "authenticated": true,
  "nonce": "abc123",
  "hash": "tx_hash...",
  "client_address": "G...",
  "timestamp": "2025-03-07T20:26:44Z",
  "domain": "example.com"
}
```

## Процесс аутентификации

1. Клиент отправляет POST запрос на /remote/sep07/auth/init с domain и nonce и salt
2. Сервер генерирует:
   - QR-код с SEP-7 URI
   - Транзакцию с двумя manage_data операциями:
     * От клиента: eurmtl.me auth = {nonce}
     * От сервера: web_auth_domain = {domain}
3. Клиент сканирует QR-код и подписывает транзакцию
4. Сервер получает подписанную транзакцию через callback
5. Клиент проверяет статус через /remote/sep07/auth/status/{nonce}

## Важные моменты

- Nonce действителен 5 минут
- QR-код содержит SEP-7 URI с XDR транзакции
- Sequence number в транзакции = 0
- Callback URL формируется как https://eurmtl.me/remote/sep07/auth/callback