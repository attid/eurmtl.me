# mountain-message-grist-notify

## Goal

Notify Telegram through Grist `Messages` when the mountain contract `message()` changes.

## Decisions

- Trigger on both mountain page load and explicit `Refresh`.
- Use `notifyinfo / Messages` in the same notify doc as the other `NOTIFY_*` tables.
- Compare against the last **our** mountain notification, not the last row in the table.
- Durable dedupe state is `comment`; in-memory cache is only an optimization.
- `messsage` is Telegram HTML:
  - prefix about message change
  - escaped message body with `<br>`
  - contract link as `<a>`
- Fixed target:
  - `chat_id = -1001429770534`
  - `reply_to = 160275`
  - `topik_id = 0`
- The sender side is triggered by expanding the existing `/grist/webhook/<table_name>` route
  with a new `NOTIFY_MESSAGES` branch.
- `NOTIFY_MESSAGES` sender behavior:
  - extract record `id` values from webhook payload
  - reload those rows from Grist before sending
  - send via `skynet_bot.send_message(..., parse_mode="HTML")`
  - write `send_date` on success
  - write `error_message` on failure
  - do not retry the same row automatically once `send_date` or `error_message` is set
  - treat `reply_to = 0` and `topik_id = 0` as “do not pass this Telegram argument”

## Verification

- `tests/services/test_mountain_contract.py`
- `tests/routers/test_contracts.py`
- `tests/test_grist_tools.py`
- `tests/routers/test_grist.py`
