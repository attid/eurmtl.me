import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_index_root(client):
    """Test root route /"""
    response = await client.get("/")
    assert response.status_code == 200
    assert 'rel="api-catalog"' in response.headers["Link"]
    assert "</llms.txt>" in response.headers["Link"]
    assert "</.well-known/stellar.toml>" in response.headers["Link"]
    assert "</.well-known/agent-skills/index.json>" in response.headers["Link"]


@pytest.mark.asyncio
async def test_index_mytest(client):
    """Test /mytest route"""
    response = await client.get("/mytest")
    assert response.status_code == 200
    assert (await response.get_data(as_text=True)) == "***"


@pytest.mark.asyncio
async def test_index_uuid(client):
    """Test /uuid route"""
    response = await client.get("/uuid")
    assert response.status_code == 200
    data = await response.get_data(as_text=True)
    assert len(data) == 32  # hex uuid is 32 chars


@pytest.mark.asyncio
async def test_index_err_no_auth(client):
    """Test /err without auth"""
    with patch("routers.index.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.get("/err")
        assert (await response.get_data(as_text=True)) == "need authority"


@pytest.mark.asyncio
async def test_index_err_with_auth_no_file(client):
    """Test /err with auth but no log file"""
    with patch("routers.index.check_user_weight", new=AsyncMock(return_value=1)):
        with patch("os.path.isfile", return_value=False):
            response = await client.get("/err")
            assert (await response.get_data(as_text=True)) == "No error"


@pytest.mark.asyncio
async def test_index_myip(client):
    """Test /myip route"""
    # Mock get_ip since it might depend on external services or request headers
    with patch("routers.index.get_ip", new=AsyncMock(return_value="127.0.0.1")):
        response = await client.get("/myip")
        assert (await response.get_data(as_text=True)) == "127.0.0.1"


@pytest.mark.asyncio
async def test_llms_txt_exposes_machine_api_overview(client):
    """Test /llms.txt machine-readable entrypoint."""
    response = await client.get("/llms.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"

    body = await response.get_data(as_text=True)
    assert "EURMTL machine API guide" in body
    assert "GET /llms.txt" in body
    assert "POST /remote/decode" in body
    assert "POST /remote/sep07/auth/init" in body
    assert "GET /.well-known/stellar.toml" in body


@pytest.mark.asyncio
async def test_llm_txt_is_not_exposed_anymore(client):
    """Test legacy /llm.txt alias is removed."""
    response = await client.get("/llm.txt")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_robots_txt_exposes_explicit_crawl_rules(client):
    """Test /robots.txt machine-readable crawl policy."""
    response = await client.get("/robots.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"

    body = await response.get_data(as_text=True)
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Allow: /.well-known/" in body
    assert "Sitemap: " in body
    assert "Content-Signal: ai-train=no, search=yes, ai-input=yes" in body
    assert "User-agent: GPTBot" in body
    assert "User-agent: OAI-SearchBot" in body
    assert "User-agent: Claude-Web" in body
    assert "User-agent: Google-Extended" in body
    assert "Disallow: /restart" in body
    assert "Disallow: /updatedb" in body
    assert "Disallow: /err" in body
    assert "Disallow: /log" in body


@pytest.mark.asyncio
async def test_sitemap_xml_lists_canonical_public_urls(client):
    """Test /sitemap.xml canonical discovery file."""
    response = await client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.mimetype == "application/xml"

    body = await response.get_data(as_text=True)
    assert "<urlset" in body
    assert "/llms.txt</loc>" in body
    assert "/.well-known/api-catalog</loc>" in body
    assert "/.well-known/agent-skills/index.json</loc>" in body


@pytest.mark.asyncio
async def test_api_catalog_exposes_linkset_metadata(client):
    """Test /.well-known/api-catalog discovery document."""
    response = await client.get("/.well-known/api-catalog")

    assert response.status_code == 200
    assert response.mimetype == "application/linkset+json"

    data = json.loads(await response.get_data(as_text=True))
    assert "linkset" in data
    entry = data["linkset"][0]
    assert entry["anchor"].endswith("/")
    assert "service-doc" in entry
    assert "service-desc" in entry
    assert "status" in entry
    assert entry["service-doc"][0]["href"].endswith("/llms.txt")
    assert entry["service-desc"][0]["href"].endswith("/openapi.json")
    assert entry["status"][0]["href"].endswith("/healthz")


@pytest.mark.asyncio
async def test_agent_skills_index_exposes_skill_and_digest(client):
    """Test /.well-known/agent-skills/index.json discovery index."""
    skill_response = await client.get("/.well-known/agent-skills/eurmtl-http/SKILL.md")
    skill_body = await skill_response.get_data()
    expected_digest = f"sha256:{hashlib.sha256(skill_body).hexdigest()}"

    response = await client.get("/.well-known/agent-skills/index.json")

    assert response.status_code == 200
    assert response.mimetype == "application/json"

    data = json.loads(await response.get_data(as_text=True))
    assert (
        data["$schema"] == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    )
    skill = data["skills"][0]
    assert skill["name"] == "eurmtl-http"
    assert skill["type"] == "skill-md"
    assert skill["url"] == "/.well-known/agent-skills/eurmtl-http/SKILL.md"
    assert skill["digest"] == expected_digest


@pytest.mark.asyncio
async def test_agent_skill_markdown_is_published(client):
    """Test published SKILL.md for agent workflows."""
    response = await client.get("/.well-known/agent-skills/eurmtl-http/SKILL.md")

    assert response.status_code == 200
    assert response.mimetype == "text/markdown"

    body = await response.get_data(as_text=True)
    assert "name: eurmtl-http" in body
    assert "GET /llms.txt" in body
    assert "POST /lab/build_xdr" in body
    assert "POST /remote/decode" in body
