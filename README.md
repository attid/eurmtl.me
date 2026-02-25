# EURMTL - Stellar MTL Platform

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Platform for Stellar network operations and MTL token management. Provides transaction signing tools, Grist integration, Telegram bot interface, and various Stellar-related utilities.

## AI-First Workflow

Repository evolves in agent-first mode with predictable, mechanically verifiable steps.

- Start from `AGENTS.md` for navigation.
- Use detailed rules in `docs/` as source of truth.
- For non-trivial work, create an execution plan in `docs/exec-plans/active/`.
- Migrate incrementally by touch: each changed file must not degrade and should improve.
- Validate changes with project commands before finishing.

Core docs:

- `docs/architecture.md`
- `docs/conventions.md`
- `docs/golden-principles.md`
- `docs/quality-grades.md`
- `docs/glossary.md`

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- Docker & Docker Compose (optional, for containerized deployment)

## Installation

```bash
# Install dependencies using uv
uv sync

# Copy and configure environment file
cp .env_sample .env
# Edit .env with your configuration (see Configuration section)
```

## Development

### Local Development

```bash
# Run application
uv run python start.py

# Run tests
just test

# Run fast test subset
just test-fast

# Format code (ruff format)
just format

# Check formatting without changing files
just fmt

# Lint code (ruff check)
just lint

# Run architecture checks
just arch-test

# Run checks only for changed Python files
just check-changed

# Full gate before PR
just check

# Run specific test file
uv run pytest tests/test_specific_file.py -v
```

### Docker Development

```bash
# Build and run tests, then start application
just run
```

## Project Structure

```
├── routers/          # Feature routes as Quart blueprints
│   ├── index.py      # Main dashboard
│   ├── sign_tools.py # Transaction signing
│   ├── rely.py       # RELY deal management
│   └── ...           # Other feature modules
├── other/            # Shared utilities
│   ├── stellar_tools.py   # Stellar SDK operations
│   ├── grist_tools.py     # Grist integration
│   ├── telegram_tools.py  # Telegram bot
│   └── ...
├── db/               # Database models and connections
│   ├── sql_models.py # SQLAlchemy models
│   └── mongo.py      # MongoDB operations
├── services/         # Business logic services
├── templates/        # Jinja2 templates
├── static/           # Static assets (QR codes, etc.)
├── tests/            # Pytest test suite
└── start.py          # Application entry point
```

## Configuration

Configuration is managed via `.env` file. See `.env_sample` for all available options.

### Key Configuration Variables

- `DB_DSN` - PostgreSQL database connection string
- `MONGO_DSN` - MongoDB connection string
- `SECRET_KEY` - Application secret key for sessions
- `SENTRY_DSN` - Sentry error tracking DSN
- `GRIST_*` - Grist spreadsheet integration settings
- `ENVIRONMENT=production` - Enable production mode (disables test session)

### Test Mode

By default (when `ENVIRONMENT` is not set to `production`), the application runs in test mode with a pre-populated test user session for development convenience.

## Documentation

For detailed documentation, architecture overview, and advanced usage:
- **[AGENTS.md](AGENTS.md)** - Short index for agents
- **[docs/architecture.md](docs/architecture.md)** - Current and target architecture
- **[docs/conventions.md](docs/conventions.md)** - Coding conventions and templates
- **[docs/golden-principles.md](docs/golden-principles.md)** - Immutable project principles
- **[docs/quality-grades.md](docs/quality-grades.md)** - Quality level by area
- **[docs/glossary.md](docs/glossary.md)** - Ubiquitous language
- **[CLAUDE.md](CLAUDE.md)** - Global local-agent constraints

## Available Commands

Run `just` or `just --list` to see all available commands:

```bash
just test        # Run full test suite
just test-fast   # Run quick test subset
just format      # Apply formatting
just fmt         # Check formatting (no writes)
just lint        # Run linter
just types       # Run pyright type checks
just arch-test   # Run structural architecture checks
just check-changed # Run checks for changed Python files
just check       # fmt + lint + types + test + arch-test
just run         # Build and run Docker image (runs tests first)
```

## License

[Add license information if applicable]
