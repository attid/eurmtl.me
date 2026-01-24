# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Package Management
- **Install dependencies**: `uv sync` (recommended)
- **Update dependencies**: `uv sync --upgrade`
- **Run with uv**: `uv run python start.py`

### Running the Application
- **Development mode**: `just dev` or `uv run python start.py`
- **Production mode**: `uv run python start.py`
- **Docker development**: `just docker-dev`
- **Docker production**: `just run`

### Testing and Quality Assurance
- **Run tests**: `just test` or `uv run pytest`
- **Run specific test**: `uv run pytest tests/test_specific_file.py -v`
- **Format code**: `just format` (Black + isort)
- **Lint code**: `just lint` (Black + isort + flake8)
- **Type checking**: `uv run mypy .` (lenient mode)

### Docker Commands
- **Build image**: `just build`
- **Run in Docker**: `just run` (includes tests)
- **Docker dev mode**: `just docker-dev`
- **Docker shell**: `just shell`
- **Stop containers**: `just docker-stop`

## Architecture Overview

### Application Structure
- **Framework**: Quart (async Flask) with SQLAlchemy
- **Entry point**: `start.py` - registers blueprints, configures Sentry, manages sessions
- **Production server**: Uvicorn with uvloop (when available)
- **Configuration**: Pydantic settings via `other/config_reader.py`

### Core Components

#### Routers (`routers/`)
Feature-based blueprints that handle specific functionality:
- `index.py` - Main dashboard and navigation
- `sign_tools.py` - Stellar transaction signing and management
- `federal.py` - Federal system operations with CORS support
- `laboratory.py` - Experimental features and testing
- `grist.py` - Grist spreadsheet integration
- `web_editor.py` - Web-based editing interface
- `helpers.py` - Utility endpoints and helpers
- `cup.py`, `decision.py`, `mmwb.py` - Domain-specific features

#### Utilities (`other/`)
Shared utilities and integrations:
- `stellar_tools.py` - Core Stellar network operations (95KB, major component)
- `grist_tools.py` - Grist API integration
- `web_tools.py` - HTTP session management with timeout handling
- `qr_tools.py` - QR code generation and management
- `cache_tools.py` - Caching utilities
- `telegram_tools.py` - Telegram bot integration

#### Database (`db/`)
- `sql_models.py` - SQLAlchemy models and schemas
- `sql_pool.py` - Database connection pooling
- `mongo.py` - MongoDB operations
- `sql_requests.py` - SQL query utilities

### Key Integrations
- **Stellar Network**: Core functionality for MTL token operations
- **Grist**: Spreadsheet data management and integration
- **Telegram**: Bot interface for notifications and interactions
- **MongoDB**: Document storage for specific features
- **PostgreSQL**: Primary relational database via SQLAlchemy
- **Sentry**: Error tracking and monitoring

### Configuration Management
- Environment-based configuration via `.env` file
- Test mode automatically enabled in non-production environments
- Test user session populated for development (`itolstov` user)
- Production detection via `ENVIRONMENT=production`

### Development Notes
- **Testing**: Use `pytest-asyncio` for async tests, mock network/IO operations
- **QR generation**: Tests write to `static/qr/` directory
- **Error handling**: Sentry with TTL cache to prevent duplicate error reporting
- **Session management**: Permanent sessions with 7-day lifetime
- **CORS**: Configured for federal system operations

### File Structure Conventions
- Routes: One feature per file in `routers/`
- Tests: Named `test_*.py` in `tests/` directory
- Static assets: QR images in `static/qr/`
- Templates: Jinja2 templates in `templates/` directory