from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part.startswith(".") for part in path.parts):
            continue
        yield path


def parse_import_targets(text: str) -> list[str]:
    pattern = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)
    return pattern.findall(text)


def check_dependency_rules() -> list[str]:
    errors: list[str] = []

    domain_dir = REPO_ROOT / "domain"
    application_dir = REPO_ROOT / "application"

    if domain_dir.exists():
        for file_path in iter_python_files(domain_dir):
            imports = parse_import_targets(file_path.read_text(encoding="utf-8"))
            for target in imports:
                if (
                    target.startswith("application")
                    or target.startswith("infrastructure")
                    or target.startswith("interface")
                ):
                    errors.append(
                        "ERROR: "
                        f"{file_path.relative_to(REPO_ROOT)} imports {target}. "
                        "Domain layer must not depend on outer layers."
                    )

    if application_dir.exists():
        for file_path in iter_python_files(application_dir):
            imports = parse_import_targets(file_path.read_text(encoding="utf-8"))
            for target in imports:
                if target.startswith("infrastructure") or target.startswith(
                    "interface"
                ):
                    errors.append(
                        "ERROR: "
                        f"{file_path.relative_to(REPO_ROOT)} imports {target}. "
                        "Application layer must not depend on interface/infrastructure implementations."
                    )

    return errors


def check_required_docs() -> list[str]:
    errors: list[str] = []
    required_files = [
        "docs/architecture.md",
        "docs/conventions.md",
        "docs/golden-principles.md",
        "docs/quality-grades.md",
        "docs/glossary.md",
    ]

    for rel_path in required_files:
        if not (REPO_ROOT / rel_path).exists():
            errors.append(f"ERROR: required file missing: {rel_path}")

    return errors


def check_forbidden_misc_dirs() -> list[str]:
    errors: list[str] = []
    forbidden_dirs = ["misc", "old", "tmp"]

    for name in forbidden_dirs:
        path = REPO_ROOT / name
        if path.exists() and path.is_dir():
            errors.append(f"ERROR: forbidden top-level directory found: {name}/")

    return errors


def main() -> int:
    errors = []
    errors.extend(check_required_docs())
    errors.extend(check_forbidden_misc_dirs())
    errors.extend(check_dependency_rules())

    if errors:
        for error in errors:
            print(error)
        return 1

    print("arch-test passed: docs baseline and architecture guardrails are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
