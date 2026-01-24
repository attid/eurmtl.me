# Repository Guidelines

## Project Structure & Module Organization
- `start.py`: Quart application entrypoint; registers blueprints and Sentry.
- `routers/`: Feature routes as Quart blueprints (e.g., `index.py`, `sign_tools.py`).
- `other/`: Shared utilities (e.g., `stellar_tools.py`, `qr_tools.py`, `config_reader.py`).
- `db/`: SQLAlchemy models and DB pool.
- `templates/` and `static/`: Jinja2 templates and assets (QR images under `static/qr/`).
- `tests/`: Pytest suite (`test_*.py`).
- `Makefile`, `Dockerfile`, `docker-compose.yml`: Dev/build tooling.

## Build, Test, and Development Commands
- `make dev`: Start in dev mode (uses `uv` and `./dev.sh`).
- `make run`: Run app locally (`uv run python start.py`).
- `make test`: Run tests.
- `make format` / `make lint`: Apply/check Black + isort + flake8.
- `make docker-build` / `make docker-run`: Build and run with Docker Compose.
- `make docker-test[-all]`: Run tests inside Docker (mounts `tests/` and `static/qr/`).

## Coding Style & Naming Conventions
- Python 3.12; 4‑space indents; line length 120.
- Use snake_case for modules/functions, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Tools: Black, isort (profile=black), flake8, mypy (lenient, `ignore_missing_imports=true`).
- Keep blueprints cohesive per file under `routers/`.
- Front-end handlers: привязывайте действия через inline `on*` атрибуты в шаблонах; навешивайте слушатели в рантайме только если другого выхода нет и обязательно фиксируйте это в код-ревью/описании.

## Testing Guidelines
- Framework: Pytest + pytest-asyncio. Tests live in `tests/`, files named `test_*.py`.
- Run: `make test` or `uv run pytest`.
- Async tests: use `pytest.mark.asyncio`. Prefer fast, isolated unit tests; mock network/IO.
- Tests that write QR files should target `static/qr/` and clean up.

## Commit & Pull Request Guidelines
- Commits: Conventional style (`feat|fix|refactor|chore(test)|docs(scope): subject`). Emojis optional (seen in history).
- Subject in imperative mood; keep related changes together.
- PRs: clear description, link issues, list changes, include screenshots for UI/template updates, and note DB/migration impacts.
- Ensure: tests pass, `make lint` is clean, and no secrets committed.

## Security & Configuration Tips
- Configuration via `.env` loaded by `other/config_reader.py` (pydantic-settings). Do not commit `.env`.
- Common vars: `DB_DSN`, `SECRET_KEY`, `SENTRY_DSN`, `MONGO_DSN`, `GRIST_*`, etc.
- Production uses Uvicorn (+ uvloop when available); set `ENVIRONMENT=production` to disable test mode sessions.

## Task Intake Protocol
- For each new task, first analyze the requirements and explicitly state which files or directories need to change.
- Do not edit any files until there is direct permission that names the specific file(s) or directory that may be modified—no exceptions.
- Before editing any file, estimate the chance the request can be interpreted in multiple ways; if there is more than a ~20% chance of ambiguity, ask the user to clarify the exact change.
