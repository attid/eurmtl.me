# D2 tx-modal: memo-in-XDR, сохранение без ухода со страницы

Дата: 2026-10-09 · Статус: в работе · Заказчик: владелец (m04259: «я должен
отсюда сам поменять мемо, потом сохранить и получить ссылку и вставить её
в текст и не потерять если случайно закрыл на крестик»)

## Проблема

Модалка «Транза…» (templates/d2_tx_modal.html) сейчас только перебрасывает
на /sign_tools с GET-параметрами. Владельцу нужно всё в модалке:

1. поменять memo в XDR (как «Insert Memo Into XDR» на tabler_sign_add);
2. сохранить транзакцию не уходя со страницы и получить ссылку
   на неё (вставить в текст вопроса);
3. случайно закрытая на крестик модалка не терять введённое.

## Контракты (существующие, не меняем)

- POST /lab/update_memo {xdr, memo} → {success, xdr} | {error}
  (routers/laboratory.py:413; валидация: memo 3..28 байт, printable).
- POST /sign_tools form(xdr, description, memo) → redirect на
  /sign_tools/<hash> (routers/sign_tools.py:228, add_transaction в
  services/stellar_client.py:666; description >= 3 символов).
  Повторный POST того же XDR — не дубликат: add_transaction возвращает
  существующий hash (repo.get_by_hash).

## Изменения

Файлы:

1. routers/sign_tools.py — в start_add_transaction: если запрос
   JSON/fetch (Accept: application/json или header X-Requested-With),
   вместо redirect вернуть jsonify({url: url_for(...show_transaction...)}).
   Ошибки — jsonify({error}) со статусом 400.
2. templates/d2_tx_modal.html:
   - кнопка «Вставить memo в XDR» у поля Memo → /lab/update_memo,
     клиентская валидация как в tabler_sign_add.html (3 символа,
     28 байт, printable), заменяет txXdr.value;
   - кнопка «Сохранить» в футере модалки вместо «Открыть в sign_tools»:
     fetch POST /sign_tools (form-encoded, X-Requested-With) → показать
     блок со ссылкой (input readonly + кнопка «Копировать»);
     повторное сохранение безопасно (та же ссылка);
   - данные модалки живут в JS-переменных, при закрытии восстанавливаются
     при повторном открытии (закрытие на крестик больше не теряет ввод);
     confirm на закрытие НЕ нужен, т.к. ввод не теряется.
3. tests/routers/test_sign_tools.py — новый тест: POST с
   X-Requested-With=XMLHttpRequest возвращает JSON {url: ...}; повторный
   POST того же XDR возвращает тот же url; без заголовка — redirect как
   раньше.

Не трогаем: tabler_sign_add.html, /lab/update_memo, контракты шаблонов.

## Приёмка

- В модалке: вставить XDR → поменять memo → «Вставить memo в XDR» →
  XDR изменился → «Сохранить» → в модалке появилась ссылка на
  /sign_tools/<hash>, страница не перезагрузилась.
- Копировать ссылку → вставить в текст вопроса.
- Закрыть модалку крестиком → открыть снова → XDR и memo на месте.
- Повторное «Сохранить» не создаёт дубликат.
- pytest зелёный, ruff зелёный, смоук на стенде :8000.
