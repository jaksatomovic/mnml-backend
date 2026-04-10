import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from api.index import app


@pytest.mark.asyncio
async def test_location_search_api_returns_candidates():
    # httpx compatibility wrapper for different versions
    try:
        from httpx import ASGITransport  # type: ignore

        transport = ASGITransport(app=app)
        make_client = lambda **kw: AsyncClient(transport=transport, base_url="http://test", **kw)
    except Exception:
        make_client = lambda **kw: AsyncClient(app=app, base_url="http://test", **kw)
    with patch("api.routes.locations.search_locations", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            {
                "city": "Pingyang",
                "display_name": "Pingyang · Zhejiang · China",
                "admin1": "Zhejiang",
                "country": "China",
                "latitude": 27.66,
                "longitude": 120.56,
                "timezone": "Asia/Shanghai",
            }
        ]
        async with make_client() as client:
            resp = await client.get("/api/locations/search", params={"q": "Pingyang", "scope": "global"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "Pingyang"
    assert data["scope"] == "global"
    assert data["items"][0]["city"] == "Pingyang"
    mock_search.assert_awaited_once_with("Pingyang", limit=8, scope="global", locale="zh")
