# Agent Skill Precedence

## Контекст
В репозитории используется внешний набор process-skills (`~/.agents/skills/superpowers/`). Нужно явно зафиксировать, что эти skills допустимы как process guidance, но не переопределяют repo-specific правила из `AI_FIRST.md`, `AGENTS.md` и `docs/`.

## План
1. [x] Минимально обновить `AGENTS.md`, добавив явное правило приоритета для external skills.
2. [x] Проверить diff и убедиться, что формулировка не конфликтует с уже существующими правилами.
3. [x] Закрыть plan после завершения.

## Результат
- В `AGENTS.md` добавлено явное правило, что external process-skills допустимы только как process guidance.
- Зафиксировано, что repo-specific правила, пути, команды и workflow из `AI_FIRST.md`, `AGENTS.md` и `docs/` имеют приоритет над generic skill defaults.

## Верификация
- `git diff --check`
- ручная проверка итоговой формулировки в `AGENTS.md`

## Файлы
- `AGENTS.md`
- `docs/exec-plans/completed/2026-04-01-agent-skill-precedence.md`
