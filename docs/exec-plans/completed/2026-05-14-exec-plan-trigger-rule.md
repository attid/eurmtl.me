# Exec plan trigger rule

## Контекст

После фикса `KeyError: 'memo_type'` plan-файл был создан только постфактум. Нужно убрать неоднозначность для будущих агентов: когда есть сомнение, создавать ли задачу, агент должен спросить; если изменение затрагивает 2+ файла и это не чистое форматирование, task/plan обязателен.

## Выполненные изменения

1. [x] Уточнить короткое правило в `AGENTS.md`.
2. [x] Добавить source-of-truth правило в `docs/conventions.md`.
3. [x] Сохранить явное исключение для чистого форматирования.

## Верификация

- `git diff -- AGENTS.md docs/conventions.md docs/exec-plans/completed/2026-05-14-exec-plan-trigger-rule.md`: проверено вручную.
- `just check-changed`: passed.
