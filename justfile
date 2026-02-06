IMAGE_NAME := "mtl_sing_tools"

default:
    @just --list

test:
    uv run --extra dev pytest

lint:
    uv run --extra dev ruff check .

format:
    uv run --extra dev ruff format .

types:
    uv run --extra dev pyright

run: test
    docker build -t {{IMAGE_NAME}}:local .
    echo http://127.0.0.1:8000
    docker run --rm --network host --env-file .env {{IMAGE_NAME}}:local

push-gitdocker tag="latest":
    docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
                 --build-arg CACHEBUST=$(git rev-parse HEAD) \
                 -t {{IMAGE_NAME}}:{{tag}} .
    docker tag {{IMAGE_NAME}} ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
    docker push ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
