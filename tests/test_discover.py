"""
Discover (modetext) texttest
"""
import json
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from api.index import app
from core.config_store import get_main_db, init_db, upsert_device_membership
from core.mode_registry import get_registry, CUSTOM_JSON_DIR
from core.stats_store import init_stats_db
from core.cache import init_cache_db

TEST_MAC = "AA:BB:CC:DD:EE:01"


@pytest.fixture
async def client(tmp_path):
    """Create an async client with isolated temp databases for each test."""
    from core import db as db_mod
    await db_mod.close_all()

    async def _normalize_configs_table():
        db = await get_main_db()
        cur = await db.execute("PRAGMA table_info(configs)")
        cols = {row[1] for row in await cur.fetchall()}
        async def _add(col: str, ddl: str):
            if col not in cols:
                await db.execute(f"ALTER TABLE configs ADD COLUMN {col} {ddl}")
        await _add("focus_listening", "INTEGER DEFAULT 0")
        await _add("latitude", "REAL")
        await _add("longitude", "REAL")
        await _add("timezone", "TEXT DEFAULT ''")
        await _add("admin1", "TEXT DEFAULT ''")
        await _add("country", "TEXT DEFAULT ''")
        await _add("is_active", "INTEGER DEFAULT 1")
        await db.commit()

    # Redirect all database paths to temp files
    test_main_db = str(tmp_path / "test_inksight.db")
    test_cache_db = str(tmp_path / "test_cache.db")

    with patch.object(db_mod, "_MAIN_DB_PATH", test_main_db), \
         patch.object(db_mod, "_CACHE_DB_PATH", test_cache_db), \
         patch("core.config_store.DB_PATH", test_main_db), \
         patch("core.stats_store.DB_PATH", test_main_db), \
         patch("core.cache._CACHE_DB_PATH", test_cache_db):
        # Initialize the databases with the temp paths
        await init_db()
        await init_stats_db()
        await init_cache_db()
        await _normalize_configs_table()

        # httpx compatibility wrapper for different versions
        try:
            from httpx import ASGITransport  # type: ignore

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
        except Exception:
            async with AsyncClient(app=app, base_url="http://test") as c:
                yield c

        # Clean up connections after each test
        await db_mod.close_all()


@pytest.fixture
def sample_date_ctx():
    """A typical date context dict."""
    return {
        "date_str": "2/16 Mon",
        "time_str": "09:30:00",
        "weekday": 0,
        "hour": 9,
        "is_weekend": False,
        "year": 2026,
        "day": 16,
        "month_cn": "February",
        "weekday_cn": "Mon",
        "day_of_year": 47,
        "days_in_year": 365,
        "festival": "",
        "is_holiday": False,
        "is_workday": True,
        "upcoming_holiday": "Qingming Festival",
        "days_until_holiday": 48,
        "holiday_date": "04/05",
        "daily_word": "spring breeze",
    }


@pytest.fixture
def sample_weather():
    """A typical weather dict."""
    return {
        "temp": 12,
        "weather_code": 1,
        "weather_str": "12°C",
    }


@pytest.fixture
async def test_user(client: AsyncClient):
    """texttesttext"""
    username = "test_discover_user"
    password = "testpass123"
    
    # text（text）
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "email": f"{username}@example.com",
        },
    )
    assert resp.status_code == 200
    
    # text token
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()["token"]
    
    # text ID
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    user_data = resp.json()

    # texttesttext，text Discover text mac text
    membership = await upsert_device_membership(
        TEST_MAC,
        user_data["user_id"],
        role="owner",
        status="active",
        nickname="DiscoverTestDevice",
    )
    assert membership["status"] == "active"

    return {
        "username": username,
        "token": token,
        "user_id": user_data["user_id"],
        "mac": TEST_MAC,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def test_custom_mode(tmp_path, client: AsyncClient, test_user):
    """texttesttextmode"""
    from pathlib import Path
    
    # textmodetext
    mode_def = {
        "mode_id": "TEST_MODE",
        "display_name": "testmode",
        "icon": "star",
        "cacheable": True,
        "description": "texttestmode",
        "content": {
            "type": "static",
            "static_data": {
                "text": "testtext",
                "title": "testtext",
            },
        },
        "layout": {
            "body": [
                {
                    "type": "text",
                    "field": "title",
                    "font_size": 16,
                    "align": "center",
                },
                {
                    "type": "text",
                    "field": "text",
                    "font_size": 12,
                    "align": "left",
                },
            ],
        },
    }
    
    # text
    custom_dir = tmp_path / "custom_modes"
    custom_dir.mkdir(exist_ok=True)
    
    with patch("core.mode_registry.CUSTOM_JSON_DIR", str(custom_dir)):
        mode_file = custom_dir / "test_mode.json"
        mode_file.write_text(json.dumps(mode_def, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # text
        registry = get_registry()
        registry.load_json_mode(str(mode_file), source="custom")
        
        yield {
            "mode_id": "TEST_MODE",
            "mode_def": mode_def,
            "file_path": str(mode_file),
        }


class TestDiscoverAPI:
    """Discover API texttest"""

    @pytest.mark.asyncio
    async def test_list_modes_empty(self, client: AsyncClient):
        """testtext"""
        resp = await client.get("/api/discover/modes")
        assert resp.status_code == 200
        data = resp.json()
        assert "modes" in data
        assert "pagination" in data
        assert len(data["modes"]) == 0
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_modes_with_category_filter(self, client: AsyncClient, test_user, test_custom_mode):
        """testtext"""
        # textmode
        resp = await client.post(
            "/api/discover/modes/publish",
            headers=test_user["headers"],
            json={
                "source_custom_mode_id": "TEST_MODE",
                "name": "testmode",
                "description": "testtext",
                "category": "productivity",
                "mac": test_user["mac"],
            },
        )
        assert resp.status_code == 200
        
        # testtext
        resp = await client.get("/api/discover/modes?category=productivity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modes"]) == 1
        assert data["modes"][0]["category"] == "productivity"
        
        # testtext
        resp = await client.get("/api/discover/modes?category=learning")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modes"]) == 0

    @pytest.mark.asyncio
    async def test_list_modes_pagination(self, client: AsyncClient, test_user, test_custom_mode):
        """testtext"""
        # textmode
        for i in range(5):
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": f"testmode {i}",
                    "description": f"testtext {i}",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            assert resp.status_code == 200
        
        # testtext
        resp = await client.get("/api/discover/modes?page=1&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modes"]) == 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 2
        assert data["pagination"]["total"] == 5

    @pytest.mark.asyncio
    async def test_publish_mode_success(self, client: AsyncClient, test_user, test_custom_mode, sample_date_ctx, sample_weather):
        """testtextmode"""
        with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
             patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
             patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
             patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gen, \
             patch("core.json_renderer.render_json_mode") as mock_render:
            
            # Mock text
            mock_gen.return_value = {
                "text": "testtext",
                "title": "testtext",
            }
            
            # Mock text
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
            mock_render.return_value = mock_img
            
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "id" in data
            
            # text generate_json_mode_content text，text LLM text（text）
            assert mock_gen.called
            call_kwargs = mock_gen.call_args[1] if mock_gen.call_args else {}
            assert "llm_provider" in call_kwargs
            assert "llm_model" in call_kwargs
            assert "api_key" in call_kwargs
            assert "image_provider" in call_kwargs
            assert "image_model" in call_kwargs
            assert "image_api_key" in call_kwargs
            
            # text
            db = await get_main_db()
            cursor = await db.execute(
                "SELECT id, name, category, author_id FROM shared_modes WHERE id = ?",
                (data["id"],),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[1] == "testmode"
            assert row[2] == "productivity"
            assert row[3] == test_user["user_id"]

    @pytest.mark.asyncio
    async def test_publish_mode_uses_user_llm_config(self, client: AsyncClient, test_user, test_custom_mode, sample_date_ctx, sample_weather):
        """testtextmodetext LLM text"""
        # Mock text LLM text
        user_llm_config = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-test-user-key-12345",
            "image_provider": "aliyun",
            "image_model": "qwen-image-max",
            "image_api_key": "sk-test-image-key-67890",
        }
        
        with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
             patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
             patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=user_llm_config), \
             patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gen, \
             patch("core.json_renderer.render_json_mode") as mock_render:
            
            # Mock text
            mock_gen.return_value = {
                "text": "testtext",
                "title": "testtext",
            }
            
            # Mock text
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
            mock_render.return_value = mock_img
            
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            
            # text generate_json_mode_content text，text LLM text
            assert mock_gen.called
            call_kwargs = mock_gen.call_args[1] if mock_gen.call_args else {}
            assert call_kwargs.get("llm_provider") == "deepseek"
            assert call_kwargs.get("llm_model") == "deepseek-chat"
            assert call_kwargs.get("api_key") == "sk-test-user-key-12345"
            assert call_kwargs.get("image_provider") == "aliyun"
            assert call_kwargs.get("image_model") == "qwen-image-max"
            assert call_kwargs.get("image_api_key") == "sk-test-image-key-67890"

    @pytest.mark.asyncio
    async def test_publish_mode_requires_auth(self, client: AsyncClient, test_custom_mode):
        """testtext"""
        # text（text headers，text cookies）
        # text，text cookies
        try:
            from httpx import ASGITransport  # type: ignore
            _clean_ctx = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={})
        except Exception:
            _clean_ctx = AsyncClient(app=app, base_url="http://test", cookies={})
        async with _clean_ctx as clean_client:
            resp = await clean_client.post(
                "/api/discover/modes/publish",
                headers={},  # text headers
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                },
            )
            assert resp.status_code == 401, f"Expected 401 but got {resp.status_code}, response: {resp.text}"

    @pytest.mark.asyncio
    async def test_publish_mode_invalid_mode(self, client: AsyncClient, test_user):
        """testtextnot foundtextmode"""
        resp = await client.post(
            "/api/discover/modes/publish",
            headers=test_user["headers"],
            json={
                "source_custom_mode_id": "NONEXISTENT_MODE",
                "name": "testmode",
                "description": "testtext",
                "category": "productivity",
                "mac": test_user["mac"],
            },
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_publish_mode_missing_params(self, client: AsyncClient, test_user):
        """testtext"""
        resp = await client.post(
            "/api/discover/modes/publish",
            headers=test_user["headers"],
            json={
                "name": "testmode",
                # text source_custom_mode_id text category
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_publish_mode_image_gen_waiting(self, client: AsyncClient, test_user, tmp_path, sample_date_ctx, sample_weather):
        """testtext"""
        from pathlib import Path
        
        # textmode
        mode_def = {
            "mode_id": "TEST_IMAGE_GEN",
            "display_name": "testtext",
            "content": {
                "type": "image_gen",
                "provider": "text2image",
                "fallback": {
                    "artwork_title": "test",
                    "image_url": "",
                    "description": "image generation in progress",
                },
            },
            "layout": {
                "body": [
                    {"type": "text", "field": "artwork_title"},
                    {"type": "image", "field": "image_url"},
                ],
            },
        }
        
        custom_dir = tmp_path / "custom_modes"
        custom_dir.mkdir(exist_ok=True)
        
        with patch("core.mode_registry.CUSTOM_JSON_DIR", str(custom_dir)):
            mode_file = custom_dir / "test_image_gen.json"
            mode_file.write_text(json.dumps(mode_def, ensure_ascii=False, indent=2), encoding="utf-8")
            
            registry = get_registry()
            registry.load_json_mode(str(mode_file), source="custom")
            
            # Mock text：text，text
            call_count = [0]
            
            async def mock_generate_content(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    # text
                    return {
                        "artwork_title": "test",
                        "image_url": "",
                        "description": "image generation in progress",
                    }
                else:
                    # text
                    return {
                        "artwork_title": "test",
                        "image_url": "https://example.com/image.png",
                        "description": "black-and-white line art",
                    }
            
            with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
                 patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
                 patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
                 patch("core.json_content.generate_json_mode_content", side_effect=mock_generate_content), \
                 patch("core.json_renderer.render_json_mode") as mock_render:
                
                from PIL import Image
                mock_img = Image.new("RGB", (400, 300), color="white")
                mock_render.return_value = mock_img
                
                resp = await client.post(
                    "/api/discover/modes/publish",
                    headers=test_user["headers"],
                    json={
                        "source_custom_mode_id": "TEST_IMAGE_GEN",
                        "name": "testtext",
                        "description": "testtext",
                        "category": "fun",
                        "mac": test_user["mac"],
                    },
                )
                
                # text，text
                assert resp.status_code == 200
                assert call_count[0] == 3  # text3 reps

    @pytest.mark.asyncio
    async def test_publish_mode_image_gen_timeout(self, client: AsyncClient, test_user, tmp_path, sample_date_ctx, sample_weather):
        """testtexttimeout"""
        from pathlib import Path
        
        mode_def = {
            "mode_id": "TEST_IMAGE_GEN_TIMEOUT",
            "display_name": "testtimeout",
            "content": {
                "type": "image_gen",
                "provider": "text2image",
                "fallback": {
                    "artwork_title": "test",
                    "image_url": "",
                    "description": "image generation in progress",
                },
            },
            "layout": {
                "body": [
                    {"type": "text", "field": "artwork_title"},
                    {"type": "image", "field": "image_url"},
                ],
            },
        }
        
        custom_dir = tmp_path / "custom_modes"
        custom_dir.mkdir(exist_ok=True)
        
        with patch("core.mode_registry.CUSTOM_JSON_DIR", str(custom_dir)):
            mode_file = custom_dir / "test_timeout.json"
            mode_file.write_text(json.dumps(mode_def, ensure_ascii=False, indent=2), encoding="utf-8")
            
            registry = get_registry()
            registry.load_json_mode(str(mode_file), source="custom")
            
            # Mock text
            async def mock_generate_content(*args, **kwargs):
                return {
                    "artwork_title": "test",
                    "image_url": "",
                    "description": "image generation in progress",
                }
            
            with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
                 patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
                 patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
                 patch("core.json_content.generate_json_mode_content", side_effect=mock_generate_content):
                
                resp = await client.post(
                    "/api/discover/modes/publish",
                    headers=test_user["headers"],
                    json={
                        "source_custom_mode_id": "TEST_IMAGE_GEN_TIMEOUT",
                        "name": "testtimeout",
                        "description": "testtext",
                        "category": "fun",
                        "mac": test_user["mac"],
                    },
                )
                
                # texttimeouttext
                assert resp.status_code == 408
                data = resp.json()
                assert "error" in data
                assert "timeout" in data["error"]

    @pytest.mark.asyncio
    async def test_install_mode_success(self, client: AsyncClient, test_user, test_custom_mode, sample_date_ctx, sample_weather):
        """testtextmode"""
        # textmode
        with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
             patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
             patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
             patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gen, \
             patch("core.json_renderer.render_json_mode") as mock_render:
            
            mock_gen.return_value = {
                "text": "testtext",
                "title": "testtext",
            }
            
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
            mock_render.return_value = mock_img
            
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            assert resp.status_code == 200
            shared_mode_id = resp.json()["id"]
            
            # textmode
            resp = await client.post(
                f"/api/discover/modes/{shared_mode_id}/install",
                headers=test_user["headers"],
                json={"mac": test_user["mac"]},
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "custom_mode_id" in data
            assert data["custom_mode_id"].startswith("CUSTOM_")
            
            # textmodetext
            registry = get_registry()
            installed_mode = registry.get_json_mode(data["custom_mode_id"])
            assert installed_mode is not None
            assert installed_mode.info.source == "custom"

    @pytest.mark.asyncio
    async def test_install_mode_requires_auth(self, client: AsyncClient, test_user, test_custom_mode, sample_date_ctx, sample_weather):
        """testtext"""
        # textmode
        with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
             patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
             patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
             patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gen, \
             patch("core.json_renderer.render_json_mode") as mock_render:
            
            mock_gen.return_value = {"text": "testtext", "title": "testtext"}
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
            mock_render.return_value = mock_img
            
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            assert resp.status_code == 200
            shared_mode_id = resp.json()["id"]
            
            # text - text，text cookies
            try:
                from httpx import ASGITransport  # type: ignore
                _clean_ctx = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={})
            except Exception:
                _clean_ctx = AsyncClient(app=app, base_url="http://test", cookies={})
            async with _clean_ctx as clean_client:
                resp = await clean_client.post(
                    f"/api/discover/modes/{shared_mode_id}/install",
                    headers={},  # text headers
                    json={"mac": TEST_MAC},
                )
                assert resp.status_code == 401, f"Expected 401 but got {resp.status_code}, response: {resp.text}"

    @pytest.mark.asyncio
    async def test_install_mode_not_found(self, client: AsyncClient, test_user):
        """testtextnot foundtextmode"""
        resp = await client.post(
            "/api/discover/modes/99999/install",
            headers=test_user["headers"],
            json={"mac": test_user["mac"]},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_list_modes_includes_author(self, client: AsyncClient, test_user, test_custom_mode, sample_date_ctx, sample_weather):
        """testtext"""
        with patch("core.context.get_date_context", new_callable=AsyncMock, return_value=sample_date_ctx), \
             patch("core.context.get_weather", new_callable=AsyncMock, return_value=sample_weather), \
             patch("core.config_store.get_user_llm_config", new_callable=AsyncMock, return_value=None), \
             patch("core.json_content.generate_json_mode_content", new_callable=AsyncMock) as mock_gen, \
             patch("core.json_renderer.render_json_mode") as mock_render:
            
            mock_gen.return_value = {"text": "testtext", "title": "testtext"}
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
            mock_render.return_value = mock_img
            
            resp = await client.post(
                "/api/discover/modes/publish",
                headers=test_user["headers"],
                json={
                    "source_custom_mode_id": "TEST_MODE",
                    "name": "testmode",
                    "description": "testtext",
                    "category": "productivity",
                    "mac": test_user["mac"],
                },
            )
            assert resp.status_code == 200
            
            # text
            resp = await client.get("/api/discover/modes")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["modes"]) == 1
            assert "author" in data["modes"][0]
            assert data["modes"][0]["author"] == f"@{test_user['username']}"
