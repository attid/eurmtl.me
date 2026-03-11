from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from other.tailscale import get_latest_version_package, normalize


def test_normalize_handles_valid_and_invalid_versions():
    assert str(normalize("1.78.3")) == "1.78.3"
    assert normalize("not-a-version") is None


@pytest.mark.asyncio
async def test_get_latest_version_package_downloads_latest(tmp_path):
    packages_text = """
Package: tailscale
Version: 1.70.0
Filename: pool/main/t/tailscale_old.deb

Package: tailscale
Version: 1.78.3
Filename: pool/main/t/tailscale_latest.deb
""".strip()

    with (
        patch("other.tailscale.start_path", str(tmp_path)),
        patch(
            "other.tailscale.http_session_manager.get_web_request",
            AsyncMock(
                side_effect=[
                    SimpleNamespace(status=200, data=packages_text),
                    SimpleNamespace(status=200, data=b"deb-bytes"),
                ]
            ),
        ),
    ):
        local_name = await get_latest_version_package()

    assert local_name == "tailscale_latest.deb"
    assert (Path(tmp_path) / "static" / local_name).read_bytes() == b"deb-bytes"


@pytest.mark.asyncio
async def test_get_latest_version_package_skips_existing_file(tmp_path):
    static_dir = Path(tmp_path) / "static"
    static_dir.mkdir()
    existing = static_dir / "tailscale_latest.deb"
    existing.write_bytes(b"already-here")

    packages_text = """
Package: tailscale
Version: 1.78.3
Filename: pool/main/t/tailscale_latest.deb
""".strip()

    with (
        patch("other.tailscale.start_path", str(tmp_path)),
        patch(
            "other.tailscale.http_session_manager.get_web_request",
            AsyncMock(return_value=SimpleNamespace(status=200, data=packages_text)),
        ) as get_request,
    ):
        local_name = await get_latest_version_package()

    assert local_name == "tailscale_latest.deb"
    assert get_request.await_count == 1


@pytest.mark.asyncio
async def test_get_latest_version_package_raises_for_bad_responses(tmp_path):
    with (
        patch("other.tailscale.start_path", str(tmp_path)),
        patch(
            "other.tailscale.http_session_manager.get_web_request",
            AsyncMock(return_value=SimpleNamespace(status=500, data="boom")),
        ),
    ):
        with pytest.raises(RuntimeError, match="Failed to fetch packages list"):
            await get_latest_version_package()
