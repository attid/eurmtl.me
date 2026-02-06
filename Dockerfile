# Используем официальный образ Python 3.12
FROM python:3.12-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    libpq-dev \
    libfbclient2 \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Создаем рабочую директорию
WORKDIR /app

# Создаем непривилегированного пользователя раньше
RUN useradd --create-home --shell /bin/bash --uid 1000 app && \
    chown -R app:app /app

# Копируем только файлы, необходимые для установки зависимостей
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app uv.lock* ./

# Переключаемся на пользователя app для установки зависимостей
USER app

# Устанавливаем зависимости Python
RUN uv sync --frozen --no-dev

# Build args for git version
ARG GIT_COMMIT=unknown
ARG CACHEBUST=unknown

# Копируем исходный код (CACHEBUST invalidates cache when code changes)
COPY --chown=app:app . .

# Сохраняем git версию в файл
RUN echo "${GIT_COMMIT}" > /app/.git_commit

# Метаданные образа
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

# Компилируем байткод и отключаем запись __pycache__ в рантайме
RUN .venv/bin/python -m compileall -q .
ENV PYTHONDONTWRITEBYTECODE=1

# Создаем необходимые директории
RUN mkdir -p static/qr log

# Открываем порт
EXPOSE 8000

# Добавляем healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Запускаем приложение напрямую без uv run (зависимости уже установлены)
CMD [".venv/bin/python", "start.py"]
