.PHONY: help install dev test format lint clean docker-build docker-run docker-dev

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Показать справку
	@echo "$(GREEN)Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Установить зависимости с uv
	@echo "$(GREEN)Установка uv и зависимостей...$(NC)"
	@if ! command -v uv &> /dev/null; then \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		export PATH="$$HOME/.cargo/bin:$$PATH"; \
	fi
	@uv sync

dev: install ## Запустить в режиме разработки
	@echo "$(GREEN)Запуск в режиме разработки...$(NC)"
	@./dev.sh

run: install ## Запустить приложение
	@echo "$(GREEN)Запуск приложения...$(NC)"
	@uv run python start.py

test: ## Запустить тесты
	@echo "$(GREEN)Запуск тестов...$(NC)"
	@uv run pytest

format: ## Форматировать код
	@echo "$(GREEN)Форматирование кода...$(NC)"
	@uv run black .
	@uv run isort .

lint: ## Проверить код линтерами
	@echo "$(GREEN)Проверка кода...$(NC)"
	@uv run black --check .
	@uv run isort --check-only .
	@uv run flake8 .

clean: ## Очистить временные файлы
	@echo "$(GREEN)Очистка временных файлов...$(NC)"
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +

docker-build: ## Собрать Docker образ
	@echo "$(GREEN)Сборка Docker образа...$(NC)"
	@docker build -t eurmtl:latest .

docker-run: ## Запустить в Docker
	@echo "$(GREEN)Запуск в Docker...$(NC)"
	@docker-compose up

docker-dev: ## Запустить в Docker (режим разработки)
	@echo "$(GREEN)Запуск в Docker (режим разработки)...$(NC)"
	@docker-compose --profile dev up eurmtl-dev

docker-stop: ## Остановить Docker контейнеры
	@echo "$(GREEN)Остановка Docker контейнеров...$(NC)"
	@docker-compose down

logs: ## Показать логи Docker контейнера
	@docker-compose logs -f eurmtl

shell: ## Открыть shell в виртуальном окружении
	@echo "$(GREEN)Открытие shell в виртуальном окружении...$(NC)"
	@uv run bash

update: ## Обновить зависимости
	@echo "$(GREEN)Обновление зависимостей...$(NC)"
	@uv sync --upgrade

docker-test: ## Запустить тесты в Docker контейнере
	@echo "$(GREEN)Сборка Docker образа для тестирования...$(NC)"
	@docker build -t eurmtl:test .
	@echo "$(GREEN)Запуск тестов в Docker контейнере...$(NC)"
	@docker run --rm \
		-v $(PWD)/static/qr:/app/static/qr \
		-v $(PWD)/tests:/app/tests \
		eurmtl:test \
		uv run pytest tests/test_qr_tools.py -v

docker-test-all: ## Запустить все тесты в Docker контейнере
	@echo "$(GREEN)Сборка Docker образа для тестирования...$(NC)"
	@docker build -t eurmtl:test .
	@echo "$(GREEN)Запуск всех тестов в Docker контейнере...$(NC)"
	@docker run --rm \
		-v $(PWD)/static/qr:/app/static/qr \
		-v $(PWD)/tests:/app/tests \
		eurmtl:test \
		uv run pytest tests/ -v

docker-shell: ## Открыть shell в Docker контейнере для отладки
	@echo "$(GREEN)Запуск shell в Docker контейнере...$(NC)"
	@docker run --rm -it \
		-v $(PWD)/static/qr:/app/static/qr \
		-v $(PWD)/tests:/app/tests \
		eurmtl:test \
		/bin/bash
