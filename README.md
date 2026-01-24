# EURMTL - Stellar MTL Platform

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Platform for Stellar network operations and MTL token management. Provides transaction signing tools, Grist integration, Telegram bot interface, and various Stellar-related utilities.

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
just dev
# or directly
uv run python start.py

# Run tests
just test

# Format code (Black + isort)
just format

# Lint code (Black + isort + flake8)
just lint

# Run specific test file
uv run pytest tests/test_specific_file.py -v
```

### Docker Development

```bash
# Build and run tests, then start application
just run

# Development mode with code hot-reload
just docker-dev

# Build Docker image
just build

# Stop Docker containers
just docker-stop

# Open shell in running container
just shell
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
- **[CLAUDE.md](CLAUDE.md)** - Complete development guide and architecture
- **[AGENTS.md](AGENTS.md)** - Repository guidelines and conventions

## Available Commands

Run `just` or `just --list` to see all available commands:

```bash
just dev         # Run in development mode
just test        # Run tests
just format      # Format code
just lint        # Lint code
just build       # Build Docker image
just run         # Build and run in Docker
just docker-dev  # Docker dev mode with hot-reload
just docker-stop # Stop containers
```

## License

[Add license information if applicable]
