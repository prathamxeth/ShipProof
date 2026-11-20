import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest.mark.asyncio
async def test_payload_limiter_boundary_and_chunked():
    """
    Comprehensive test of the ASGI PayloadSizeLimitMiddleware:
    1. 9 MB request accepted (not 413).
    2. Exactly 10 MB boundary accepted (not 413).
    3. 10 MB + 1 byte rejected with 413.
    4. 11 MB Content-Length rejected immediately with 413.
    5. 11 MB chunked request without Content-Length rejected with 413.
    6. Missing Content-Length request within bounds accepted.
    7. Invalid Content-Length rejected with 400.
    8. Negative Content-Length rejected with 400.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 9 MB request with Content-Length (must not be 413)
        headers_9mb = {
            "Content-Length": str(9 * 1024 * 1024),
            "Content-Type": "application/json"
        }
        # Note: /api/runs may fail auth or json parse, but MUST NOT return 413
        resp_9mb = await client.post("/api/runs", headers=headers_9mb, content=b"{}")
        assert resp_9mb.status_code != 413, f"9MB was unexpectedly rejected with 413: {resp_9mb.status_code}"

        # 2. Exactly 10 MB boundary (10 * 1024 * 1024 bytes)
        exact_10mb = 10 * 1024 * 1024
        headers_10mb = {
            "Content-Length": str(exact_10mb),
            "Content-Type": "application/json"
        }
        resp_10mb = await client.post("/api/runs", headers=headers_10mb, content=b"{}")
        assert resp_10mb.status_code != 413, "Exactly 10MB boundary was unexpectedly rejected with 413"

        # 3. 10 MB + 1 byte with Content-Length -> strictly 413
        headers_10mb_plus_1 = {
            "Content-Length": str(exact_10mb + 1),
            "Content-Type": "application/json"
        }
        resp_10mb_plus_1 = await client.post("/api/runs", headers=headers_10mb_plus_1, content=b"{}")
        assert resp_10mb_plus_1.status_code == 413
        assert "exceeds 10MB limit" in resp_10mb_plus_1.json()["detail"]

        # 4. 11 MB Content-Length -> strictly 413
        headers_11mb = {
            "Content-Length": str(11 * 1024 * 1024),
            "Content-Type": "application/json"
        }
        resp_11mb = await client.post("/api/runs", headers=headers_11mb, content=b"{}")
        assert resp_11mb.status_code == 413

        # 5. 11 MB chunked request (Streaming without Content-Length) -> strictly 413
        async def chunked_11mb():
            chunk = b" " * (1024 * 1024)  # 1 MB chunk
            for _ in range(11):
                yield chunk

        resp_chunked_11mb = await client.post(
            "/api/runs",
            content=chunked_11mb(),
            headers={"Content-Type": "application/json"}
        )
        assert resp_chunked_11mb.status_code == 413
        assert "exceeds 10MB limit" in resp_chunked_11mb.json()["detail"]

        # 6. Chunked request within bounds (2 MB) -> accepted past middleware
        async def chunked_2mb():
            chunk = b" " * (512 * 1024)  # 512 KB
            for _ in range(4):
                yield chunk

        resp_chunked_2mb = await client.post(
            "/api/runs",
            content=chunked_2mb(),
            headers={"Content-Type": "application/json"}
        )
        assert resp_chunked_2mb.status_code != 413

        # 7. Invalid Content-Length -> 400 Bad Request
        resp_invalid_cl = await client.post("/api/runs", headers={"Content-Length": "not-a-number"})
        assert resp_invalid_cl.status_code == 400
        assert "invalid Content-Length" in resp_invalid_cl.json()["detail"]

        # 8. Negative Content-Length -> 400 Bad Request
        resp_neg_cl = await client.post("/api/runs", headers={"Content-Length": "-500"})
        assert resp_neg_cl.status_code == 400
        assert "cannot be negative" in resp_neg_cl.json()["detail"]
