# 2026-10-18 — Анти-SSRF валидация callback-URL (submit_signed)

## Контекст инцидента

Задача #88 (Docker3/Sentry #3121): публичный эндпоинт
`POST /remote/sep07/submit-signed` принимает `callback_url` из тела запроса и
безусловно делает на него исходящий `POST` (`routers/remote_sep07.py`,
`submit_signed`). Атакующий использовал это как SSRF-прокси: читал
cloud-metadata (`169.254.169.254`), сканировал внутренние порты (в т.ч.
`127.0.0.1:2019` — admin API Caddy). 66 запросов за 43 минуты.

## Причина

В `submit_signed` отсутствует какая-либо проверка назначения URL: ни схемы,
ни хоста, ни резолва. `aiohttp` резолвит и коннектится к любому адресу,
включая private/loopback/link-local.

## Согласованное решение

Новый модуль `other/url_safety.py` (утилита без побочных эффектов, слой
`other` — рядом с `web_tools.py`, который уже импортирует роутер):

1. `is_blocked_ip(ip)` — блокирует всё, что не является глобально
   маршрутизируемым unicast: явные сети RFC1918, loopback, link-local,
   IPv6 `fe80::/10`, cloud-metadata, CGNAT `100.64.0.0/10`, multicast,
   reserved, unspecified, IPv4-mapped IPv6 (`::ffff:169.254.169.254`).
2. `is_blocked_hostname(host)` — `localhost`, `*.localhost`, `*.local`,
   `*.internal`, `*.home.arpa`, `*.lan`, `*.intranet`, односоставные имена
   (`metadata`, `2130706433`, docker service names) — нормализация
   регистра, trailing dot, `%zone`.
3. `validate_callback_url(url)` (async) — pre-flight: схема только
   `http`/`https`, хост не блокирован, все IP из DNS-резолва не блокированы.
   Блокировка → `CallbackURLNotAllowed` → HTTP 400
   `callback URL is not allowed`.
4. `SafeResolver(DefaultResolver)` + `create_safe_connector()` — валидация
   **в момент connect**: резолвер aiohttp проверяет имя и каждый
   полученный IP перед установкой соединения. Закрывает DNS rebinding
   (TOCTOU между pre-flight и connect). Соединение идёт на проверенный IP
   с сохранением исходного `Host`/SNI (URL не переписывается).
   `aiohttp` оборачивает `OSError` из резолвера в
   `ClientConnectorDNSError`, роутер распознаёт `CallbackURLNotAllowed`
   в `os_error` и отдаёт тот же 400.

## Изменения

- `other/url_safety.py` — новый модуль (валидатор + резолвер + коннектор).
- `routers/remote_sep07.py` — `submit_signed`: pre-flight валидация после
  проверки base64 XDR (чтобы существующий тест на base64 не ходил в DNS),
  `ClientSession(connector=create_safe_connector())`, маппинг
  connect-time блокировки в 400. Логирование callback-ответов не меняется.
- `tests/test_url_safety.py` — unit: IP/hostname-матрица, схема, резолв в
  private IP, `SafeResolver` (connect-time).
- `tests/routers/test_remote_sep07.py` — интеграционные кейсы эндпоинта
  (169.254.169.254, 127.0.0.1:2019, 10.x, 172.17.x, 192.168.x, fe80::,
  DNS rebinding, внешний HTTPS OK, connect-time rebinding → 400).
- `docs/architecture.md` — зафиксировать границу «исходящие запросы на
  пользовательский URL только через `other/url_safety.py`».

## Что НЕ меняется

- Логирование callback-ответов (`Callback response status/text`) — как есть.
- Authelia middleware — не включаем, эндпоинт остаётся публичным.
- Внешние `https://` callback-URL работают без изменений (только
  `http`/`https`, redirects не запрещаем — каждый хоп проверяется
  валидирующим коннектором).
- Таймауты/контракт ответов не меняются (нет новых полей в успешном ответе).

## Проверки

- `pytest tests/test_url_safety.py tests/routers/test_remote_sep07.py -q`.
- Полный `pytest` (критерий приёмки), `ruff check`, `ruff format --check`,
  `pyright` на изменённых файлах, `just arch-test`.
- Ручной сценарий #88: перебор `127.0.0.1:<port>` и `169.254.169.254` →
  все 400, наружу запросов нет.

## Результаты проверок

- `pytest tests/test_url_safety.py tests/routers/test_remote_sep07.py` — 103 passed.
- Полный `pytest` — 691 passed, 1 skipped (coverage 71.14%, порог 30%).
- `ruff check` / `ruff format --check` по изменённым файлам — чисто.
- `pyright` (с интерпретатором `.venv`) по изменённым файлам — 0 errors.
- `.linters/arch_test.py` — passed.
- Аудит других исходящих запросов: единственный эндпоинт, делающий
  POST на URL из запроса, — `submit_signed`. `routers/web_editor.py`
  (captcha), `other/stellar_soroban.py`, `other/web_tools.py`
  (Horizon/IPFS) ходят на константные URL — изменения не требуются.

## Раунд 2 — Code Review (P1: обход через редиректы)

Замечание: `session.post` по умолчанию следовал редиректам, а
`TCPConnector._resolve_host` для IP-литералов возвращает адрес напрямую,
минуя `SafeResolver`. Значит, публичный callback с
`Location: http://169.254.169.254/...` (в т.ч. 307/308 с сохранением POST)
снова давал SSRF.

Исправлено:
- `post_callback` в `other/url_safety.py`: `allow_redirects=False`, ручной
  цикл (лимит 10, как дефолт aiohttp). Каждый `Location` (включая
  относительный/protocol-relative через `urljoin`) валидируется
  `validate_callback_url` до запроса. Семантика как у aiohttp: 301/302
  после POST и 303 → GET без тела, 307/308 сохраняют POST и тело.
  Небезопасная схема/внутренний адрес → `CallbackURLNotAllowed` → 400;
  зацикленные редиректы → `CallbackRedirectLimitExceeded` → 500.
- `SafeConnector(aiohttp.TCPConnector)` — проверка IP-литералов в
  `_resolve_host` (defense in depth: `SafeResolver` для литералов не
  вызывается).
- Роутер `submit_signed` переведён на `post_callback`; порядок/текст
  логов callback-ответа не изменён.

Тесты: `tests/routers/test_remote_sep07.py` — редиректы (301/302/303/307/308)
на metadata, loopback, RFC1918, `fe80::`, `localhost`, userinfo-трюк,
protocol-relative, `file:` → 400 и ровно один (внешний) запрос; DNS
rebinding на редиректе → 400; 307 на внешний HTTPS сохраняет POST; 302 →
GET с относительным `Location`; лимит редиректов → 500. Плюс unit-тест
`SafeConnector` на IP-литерал без вызова резолвера.
