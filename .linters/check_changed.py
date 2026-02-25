from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_git_command(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_changed_python_files() -> list[str]:
    tracked = run_git_command(["diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"])
    untracked = run_git_command(["ls-files", "--others", "--exclude-standard"])
    paths = sorted({*tracked, *untracked})

    return [
        path for path in paths if path.endswith(".py") and (REPO_ROOT / path).exists()
    ]


def run_command(command: list[str]) -> int:
    process = subprocess.run(command, cwd=REPO_ROOT)
    return process.returncode


def main() -> int:
    changed_python = get_changed_python_files()
    if not changed_python:
        print("check-changed: no changed Python files")
        return 0

    print("check-changed: Python files")
    for path in changed_python:
        print(f"- {path}")

    format_check_cmd = [
        "uv",
        "run",
        "--extra",
        "dev",
        "ruff",
        "format",
        "--check",
        *changed_python,
    ]
    lint_check_cmd = ["uv", "run", "--extra", "dev", "ruff", "check", *changed_python]

    print("check-changed: running format check")
    if run_command(format_check_cmd) != 0:
        return 1

    print("check-changed: running lint check")
    if run_command(lint_check_cmd) != 0:
        return 1

    print("check-changed: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
