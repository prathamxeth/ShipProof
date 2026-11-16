import pytest
from starlette.applications import Starlette
from starlette.responses import RedirectResponse
from starlette.routing import Route
from httpx import AsyncClient, ASGITransport
from backend.app.core.url_validator import validate_target_url
from backend.app.core.errors import ShipProofException

def test_adversarial_ssrf_alternative_ip_representations():
    """
    Verifies that alternative IP representations (decimal, hex, octal, IPv4-mapped IPv6)
    cannot bypass metadata or private network protections.
    """
    # 1. Decimal IP for 127.0.0.1 (2130706433)
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://2130706433:8000", allow_local=False)
    assert "SSRF Protection" in str(exc.value)

    # 2. Hex IP for 127.0.0.1 (0x7f000001)
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://0x7f000001:8000", allow_local=False)
    assert "SSRF Protection" in str(exc.value)

    # 3. Decimal IP for 169.254.169.254 (2852039166) - must fail in ALL modes including allow_local=True
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://2852039166", allow_local=True)
    assert "metadata" in str(exc.value).lower() or "strictly prohibited" in str(exc.value)

    # 4. IPv4-mapped IPv6 for loopback [::ffff:127.0.0.1]
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://[::ffff:127.0.0.1]:8000", allow_local=False)
    assert "SSRF Protection" in str(exc.value)

    # 5. IPv4-mapped IPv6 for metadata [::ffff:169.254.169.254]
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://[::ffff:169.254.169.254]", allow_local=True)
    assert "metadata" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

def test_adversarial_ssrf_schemes_and_ports():
    """
    Verifies rejection of non-HTTP schemes and dangerous port boundaries.
    """
    dangerous_schemes = [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_flushall",
        "javascript:alert(document.domain)",
        "ftp://internal.mirror/firmware.bin",
        "data:text/html,<script>alert(1)</script>",
        "ldap://127.0.0.1:389/o=anonymous"
    ]
    for url in dangerous_schemes:
        with pytest.raises(ShipProofException) as exc:
            validate_target_url(url)
        assert "only HTTP and HTTPS protocols are permitted" in str(exc.value)

    # Port out of bounds
    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://example.com:0")
    assert "port" in str(exc.value).lower() and "65535" in str(exc.value)

    with pytest.raises(ShipProofException) as exc:
        validate_target_url("http://example.com:70000")
    assert "port" in str(exc.value).lower() and "65535" in str(exc.value)

@pytest.mark.asyncio
async def test_browser_redirect_egress_boundary_demonstration():
    """
    Adversarial demonstration:
    Shows that pre-execution URL validation accepts the initial public/permitted URL,
    but an HTTP client following 302 redirects will attempt to egress
    to the target of the redirect. Proves why network-level egress enforcement is necessary.
    """
    async def redirect_endpoint(request):
        return RedirectResponse("http://169.254.169.254/latest/meta-data/", status_code=302)

    redirect_app = Starlette(routes=[Route("/redirect-to-metadata", redirect_endpoint)])

    # 1. URL validation evaluates the start URL
    # A permitted target URL passes initial pre-execution validation
    start_url = "http://127.0.0.1/redirect-to-metadata"
    validated = validate_target_url(start_url, allow_local=True)
    assert validated == start_url

    # 2. However, upon HTTP request, the target server issues a 302 to 169.254.169.254
    transport = ASGITransport(app=redirect_app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        resp = await client.get("/redirect-to-metadata", follow_redirects=False)
        assert resp.status_code == 302
        redirect_target = resp.headers.get("location")
        assert redirect_target == "http://169.254.169.254/latest/meta-data/"

        # Evaluating the redirect destination reveals the SSRF attempt
        with pytest.raises(ShipProofException) as exc:
            validate_target_url(redirect_target, allow_local=True)
        assert "metadata" in str(exc.value).lower()

        # This test conclusively proves:
        # Pre-execution URL validation alone cannot prevent in-browser 302 redirect egress.
        # Host/network-level egress firewalling is an indispensable requirement for multi-tenant SaaS.
