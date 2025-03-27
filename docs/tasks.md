# Файл задач (tasks.md)

Этот файл содержит описание реализованных задач и изменений в проекте.
Используется для документирования работы и быстрого восстановления контекста.

---

# Задача 1: Добавление операции Liquidity Pool Deposit

- Добавлена карточка для операции в static/js/main.js:
  - Функция generateCardLiquidityPoolDeposit()
  - Обработка в getCardByName()

- Добавлен пункт в выпадающий список операций в templates/tabler_laboratory.html

- Реализована серверная обработка в other/stellar_tools.py:
  - Добавлен case для 'liquidity_pool_deposit' в stellar_build_xdr()
  - Используется append_liquidity_pool_deposit_op()

- Параметры операции:
  - liquidity_pool_id: ID пула ликвидности
  - max_amount_a: Максимальное количество первого актива
  - max_amount_b: Максимальное количество второго актива
  - min_price: Минимальная цена
  - max_price: Максимальная цена

---

# Задача 2: Реализация компонента для работы с пулами ликвидности

- Добавлена функция generatePoolSelector в static/js/main.js:
  - Поле ввода + кнопка выбора из списка + кнопка просмотра
  - Аналогично generateAssetSelector, но для пулов

- Реализованы вспомогательные функции:
  - viewPool: открывает пул в Stellar Expert
  - fetchPoolsMTL: получает список пулов через /lab/mtl_pools

- Использует существующий endpoint /lab/mtl_pools

- Реализован автоматический расчет цен:
  - При min_price/max_price=0 используются цены +/-5% от текущей
  - Добавлена функция get_pool_price для получения текущей цены
  - В случае ошибки используется цена по умолчанию 1.0


---

# Задача 3: Добавление операции Liquidity Pool Withdraw

- Добавлена карточка для операции в static/js/main.js:
  - Функция generateCardLiquidityPoolWithdraw()
  - Обработка в getCardByName()

- Добавлен пункт в выпадающий список операций в templates/tabler_laboratory.html

- Реализована серверная обработка в other/stellar_tools.py:
  - Добавлен case для 'liquidity_pool_withdraw' в stellar_build_xdr()
  - Используется append_liquidity_pool_withdraw_op()

- Параметры операции:
  - liquidity_pool_id: ID пула ликвидности
  - amount: Количество долей пула для вывода
  - min_amount_a: Минимальное количество первого актива
  - min_amount_b: Минимальное количество второго актива

- Добавлен авто-расчет min_amount_a/b при значении 0

---

# Задача 4: Добавление операции Create Trustline Pool

- Добавлен пункт в выпадающий список операций в templates/tabler_laboratory.html
  - Использован существующий пункт liquidity_pool_trustline

- Реализована серверная обработка в other/stellar_tools.py:
  - Добавлен case для 'liquidity_pool_trustline' в stellar_build_xdr()
  - Используется append_change_trust_op() с Asset.pool_shares()

- В static/js/main.js:
  - Используется существующая функция generateCardLiquidityPoolTrustline()
  - Добавлена обработка в getCardByName()

---

# Задача 5: Добавление ручного управления sequence

- Добавлено поле sequence в форму generateCardFirst() в static/js/main.js:
  - Поле ввода с типом text (для поддержки больших чисел)
  - Подсказка "Set to 0 for automatic sequence generation from horizon"
  - Значение по умолчанию 0
  - Кнопка обновления sequence с прямым запросом к horizon.stellar.org

- Добавлена функция fetchSequence():
  - Получает текущий sequence из горизонта для указанного аккаунта
  - Корректно обрабатывает большие числа (BigInt)
  - Добавляет 1 к sequence и устанавливает в поле ввода
  - Валидация publicKey перед запросом

- Модифицирована функция gatherData():
  - Проверка валидности sequence (число >= 0)
  - Корректная обработка больших чисел

- Обновлена функция stellar_build_xdr() в other/stellar_tools.py:
  - При sequence > 0 использует указанное значение
  - При sequence = 0 загружает из горизонта
  - Поддержка обоих вариантов создания транзакции

- Логика работы:
  - 0 - автоматическая генерация sequence из горизонта
  - >0 - использование указанного значения sequence
  - Кнопка обновления для удобного получения sequence + 1
