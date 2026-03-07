import os

from other.config_reader import get_secrets_dir


def test_get_secrets_dir_returns_none_when_directory_missing(monkeypatch):
    monkeypatch.setattr(os.path, "isdir", lambda path: False)

    assert get_secrets_dir() is None


def test_get_secrets_dir_returns_run_secrets_when_directory_exists(monkeypatch):
    monkeypatch.setattr(os.path, "isdir", lambda path: path == "/run/secrets")

    assert get_secrets_dir() == "/run/secrets"
