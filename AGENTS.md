# AI-First Repo Guide

Этот файл - короткая карта для агента. Детали и правила находятся в `docs/`.
Если есть конфликт между этим файлом и `docs/`, источником правды является `docs/`.

## 0) Main Principle
- Predictability first: не угадывать формат/архитектуру, а смотреть контракты и документацию.
- Mechanical enforcement: важные правила должны проверяться командами, тестами или CI.
- Depth-first: если задача буксует, добавляем инструмент/документацию/проверку, а не ручной хаос.

## 1) Repository Map
- `README.md` - вход в проект, запуск, команды.
- `AGENTS.md` - короткая карта для агента.
- `docs/architecture.md` - текущая архитектура и целевая модель.
- `docs/conventions.md` - стиль и рабочие шаблоны.
- `docs/golden-principles.md` - неизменяемые принципы.
- `docs/quality-grades.md` - оценка качества по зонам.
- `docs/glossary.md` - единый словарь терминов.
- `docs/exec-plans/active/` - активные планы задач.
- `docs/exec-plans/completed/` - завершенные планы.
- `docs/runbooks/` - инструкции по типовым инцидентам.
- `adr/` - архитектурные решения (1 файл = 1 решение).
- `.linters/` - структурные проверки и guardrails.

## 2) Current Code Layout
- `start.py` - Quart entrypoint.
- `routers/` - web-blueprints (входные порты интерфейса).
- `services/` - прикладные сценарии/use-case orchestration.
- `other/` - интеграции и утилиты (Stellar, Grist, Telegram, cache).
- `db/` - persistence слой.
- `templates/` + `static/` - web interface.
- `tests/` - pytest-спецификация поведения.

## 3) Commands (Current Baseline)
- `just fmt` - проверка форматирования (`ruff format --check`).
- `just test` - тесты (`uv run --extra dev pytest`).
- `just test-fast` - быстрый набор (`pytest tests -q --maxfail=1`).
- `just lint` - линт (`uv run --extra dev ruff check .`).
- `just format` - форматирование (`uv run --extra dev ruff format .`).
- `just types` - проверка типов (`uv run --extra dev pyright`).
- `just arch-test` - структурные проверки (`.linters/arch_test.py`).
- `just check-changed` - проверки только для измененных Python-файлов.
- `just check` - полная проверка (`fmt-check + lint + types + test + arch-test`).
- `just run` - контейнерный запуск с предварительным `test`.
- После `git push` агент должен по умолчанию выполнять `just push-gitdocker`, если пользователь явно не отменил этот шаг.

## 4) Working Rules For Agents
- Сначала анализ и явный список файлов, которые нужно менять.
- До правок запрашивать прямое разрешение с перечислением файлов/директорий.
- Если неоднозначность >20%, задать уточнение до правок.
- Минимальный дифф, без массового форматирования и без "косметических" рефакторингов.
- Для нетривиальной задачи - создать plan-файл в `docs/exec-plans/active/`.
- Если есть сомнение, нужен ли plan-файл, спросить пользователя до правок.
- Если нужно менять 2+ файла исходного кода/тестов/шаблонов/скриптов и это не чистое форматирование, plan-файл обязателен.
- Изменения только в `.md` не требуют plan-файла сами по себе.
- Rule of touch: каждый измененный файл не ухудшается и улучшается минимум на один шаг к целевой архитектуре.
- После изменений - запустить релевантные проверки и зафиксировать результат.
- External process-skills (например, `~/.agents/skills/superpowers/`) можно использовать только как process guidance; они не переопределяют repo-specific правила, пути, команды и workflow из `AI_FIRST.md`, `AGENTS.md` и `docs/`.

## 5) Boundaries And Safety
- Без явной команды нельзя менять публичные контракты без синхронного обновления спецификаций/docs.
- Нельзя отключать линтеры/тесты для "зеленого" CI.
- Нельзя добавлять внешние зависимости без ADR.
- Нельзя трогать секреты и production-конфиги.

## 6) Done Criteria
- План создан/обновлен.
- Код и тесты синхронизированы.
- Документация актуальна.
- Проверки пройдены.
- Коммит/PR объясняет что, почему и как проверено.
