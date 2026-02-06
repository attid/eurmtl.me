IMAGE_NAME := "mtl_sing_tools"

# Default target - list all commands
default:
    @just --list

# Local development targets
dev:
    # Run application in development mode
    uv run python start.py

test:
    # Run tests with pytest
    uv run pytest

format:
    # Format code with Black and isort
    uv run black .
    uv run isort .

lint:
    # Lint code with Black, isort, and flake8
    uv run black --check .
    uv run isort --check .
    uv run flake8 .

# Docker targets
build tag="latest":
    # Build Docker image
    docker build -t {{IMAGE_NAME}}:{{tag}} .

run: test
    # Build and run Docker container
    docker build -t {{IMAGE_NAME}}:local .
    echo http://127.0.0.1:8000
    docker run --rm --network host --env-file .env {{IMAGE_NAME}}:local

docker-dev:
    # Run in Docker development mode with code mounted
    docker-compose --profile dev up eurmtl-dev

shell:
    # Open a shell into the running container
    docker-compose exec {{IMAGE_NAME}} sh

docker-stop:
    # Stop Docker containers
    docker-compose down

# Cleanup targets
clean-docker:
    # Clean up Docker images and containers
    docker system prune -f
    docker volume prune -f

# Publishing
push-gitdocker tag="latest":
    # Build with fresh code (keeps dependency cache) and push
    docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
                 --build-arg CACHEBUST=$(git rev-parse HEAD) \
                 -t {{IMAGE_NAME}}:{{tag}} .
    docker tag {{IMAGE_NAME}} ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
    docker push ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}