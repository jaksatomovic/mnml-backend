"""
testtext：
- text（text/text）
- text
- API text（text、text、text）
- text
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.config_store import (
    init_db,
    init_user_api_quota,
    get_user_api_quota,
    consume_user_free_quota,
    get_quota_owner_for_mac,
    create_user,
    authenticate_user,
)
from core.db import get_main_db


@pytest.fixture(autouse=True)
async def use_memory_db(tmp_path):
    """Redirect all DB operations to an isolated temp file per test."""
    from core import db as db_mod

    db_path = str(tmp_path / "test.db")
    await db_mod.close_all()
    with patch.object(db_mod, "_MAIN_DB_PATH", db_path), \
         patch("core.config_store.DB_PATH", db_path), \
         patch("core.stats_store.DB_PATH", db_path):
        yield db_path
    await db_mod.close_all()


class TestUserRegistration:
    """testtext（text，texttesttext）"""

    @pytest.mark.asyncio
    async def test_register_without_invite_code(self):
        """testtext（text 50）"""
        await init_db()
        
        from api.routes.auth import auth_register
        from fastapi import Response
        
        body = {
            "username": "testuser2",
            "password": "testpass123",
            "email": "test@example.com",
        }
        response = Response()
        result = await auth_register(body, response)
        
        assert result["ok"] is True
        user_id = result["user_id"]
        
        # text 50
        quota = await get_user_api_quota(user_id)
        assert quota is not None
        assert quota["free_quota_remaining"] == 50
        assert quota["total_calls_made"] == 0

    @pytest.mark.asyncio
    async def test_register_phone_email_validation(self):
        """testtext"""
        await init_db()
        
        from api.routes.auth import auth_register
        from fastapi import Response
        from fastapi.responses import JSONResponse
        
        # testinvalidtext
        body1 = {
            "username": "testuser5",
            "password": "testpass123",
            "email": "invalid-email",
        }
        response1 = Response()
        result1 = await auth_register(body1, response1)
        assert isinstance(result1, JSONResponse)
        assert result1.status_code == 400
        assert "text" in result1.body.decode()

        # testtext
        body2 = {
            "username": "testuser6",
            "password": "testpass123",
        }
        response2 = Response()
        result2 = await auth_register(body2, response2)
        assert isinstance(result2, JSONResponse)
        assert result2.status_code == 400
        assert "text" in result2.body.decode()

        # testinvalidtext（email text phone invalid）
        body3 = {
            "username": "testuser7",
            "password": "testpass123",
            "email": "valid@example.com",
            "phone": "1234567890",
        }
        response3 = Response()
        result3 = await auth_register(body3, response3)
        assert isinstance(result3, JSONResponse)
        assert result3.status_code == 400
        assert "text" in result3.body.decode()

    @pytest.mark.asyncio
    async def test_register_supports_phone_region_and_normalizes(self):
        await init_db()

        from api.routes.auth import auth_register
        from fastapi import Response

        response = Response()
        result = await auth_register(
            {
                "username": "intluser",
                "password": "testpass123",
                "email": "intluser@example.com",
                "phone": "415 555 2671",
                "phone_region": "US",
            },
            response,
        )
        assert result["ok"] is True

        db = await get_main_db()
        cursor = await db.execute("SELECT phone FROM users WHERE id = ?", (result["user_id"],))
        row = await cursor.fetchone()
        assert row[0] == "+14155552671"

    @pytest.mark.asyncio
    async def test_register_keeps_legacy_cn_input_compatible(self):
        await init_db()

        from api.routes.auth import auth_register
        from fastapi import Response

        response = Response()
        result = await auth_register(
            {
                "username": "cnuser",
                "password": "testpass123",
                "email": "cnuser@example.com",
                "phone": "13800138000",
            },
            response,
        )
        assert result["ok"] is True

        db = await get_main_db()
        cursor = await db.execute("SELECT phone FROM users WHERE id = ?", (result["user_id"],))
        row = await cursor.fetchone()
        assert row[0] == "+8613800138000"

    @pytest.mark.asyncio
    async def test_register_blocks_duplicate_against_legacy_cn_storage(self):
        await init_db()

        user_id = await create_user("legacyuser", "testpass123", phone="13800138000")
        assert user_id is not None

        from api.routes.auth import auth_register
        from fastapi import Response
        from fastapi.responses import JSONResponse

        response = Response()
        result = await auth_register(
            {
                "username": "newuser",
                "password": "testpass123",
                "email": "newuser@example.com",
                "phone": "+8613800138000",
            },
            response,
        )
        assert isinstance(result, JSONResponse)
        assert result.status_code == 409


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_reset_password_with_email_verification(self):
        await init_db()

        from api.routes.auth import auth_register, auth_reset_send_code, auth_reset_password
        from core.email import _pending_codes
        from fastapi import Response

        register_response = Response()
        register_result = await auth_register(
            {
                "username": "resetuser",
                "password": "oldpass123",
                "email": "resetuser@example.com",
            },
            register_response,
        )
        assert register_result["ok"] is True

        send_result = await auth_reset_send_code({"email": "resetuser@example.com"})
        assert send_result["ok"] is True

        code = _pending_codes["resetuser@example.com"][0]

        reset_result = await auth_reset_password(
            {"email": "resetuser@example.com", "code": code, "password": "newpass123"}
        )
        assert reset_result["ok"] is True

        user = await authenticate_user("resetuser", "newpass123")
        assert user is not None

    @pytest.mark.asyncio
    async def test_reset_password_wrong_code_rejected(self):
        await init_db()

        from api.routes.auth import auth_register, auth_reset_send_code, auth_reset_password
        from fastapi import Response
        from fastapi.responses import JSONResponse

        register_response = Response()
        await auth_register(
            {
                "username": "resetuser2",
                "password": "oldpass123",
                "email": "resetuser2@example.com",
            },
            register_response,
        )
        await auth_reset_send_code({"email": "resetuser2@example.com"})

        reset_result = await auth_reset_password(
            {"email": "resetuser2@example.com", "code": "000000", "password": "newpass123"}
        )
        assert isinstance(reset_result, JSONResponse)
        assert reset_result.status_code == 400


class TestInviteCodeRedemption:
    """testtext"""

    @pytest.mark.asyncio
    async def test_redeem_valid_invite_code(self):
        """testtext"""
        await init_db()
        db = await get_main_db()
        
        # 1. text（text，text 0）
        user_id = await create_user("testuser", "testpass", email="test@example.com")
        assert user_id is not None
        
        # 2. text
        await db.execute(
            """
            INSERT INTO invitation_codes (code, is_used, generated_at)
            VALUES (?, 0, datetime('now'))
            """,
            ("REDEEM123",),
        )
        await db.commit()
        
        # 3. text（text require_user text）
        from api.routes.auth import auth_redeem_invite_code
        from unittest.mock import patch
        
        body = {"invite_code": "REDEEM123"}
        
        # text require_user text user_id
        with patch("api.routes.auth.require_user", return_value=user_id):
            result = await auth_redeem_invite_code(body, user_id)
        
        # 4. text
        assert result["ok"] is True
        assert "text" in result["message"]
        assert result["free_quota_remaining"] == 50
        
        # 5. text
        cursor = await db.execute(
            "SELECT is_used, used_by_user_id FROM invitation_codes WHERE code = ?",
            ("REDEEM123",),
        )
        row = await cursor.fetchone()
        assert row[0] == 1
        assert row[1] == user_id
        
        # 6. text
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 50

    @pytest.mark.asyncio
    async def test_redeem_invalid_invite_code(self):
        """testtextinvalidtext"""
        await init_db()
        user_id = await create_user("testuser2", "testpass", phone="13800138000")
        
        from api.routes.auth import auth_redeem_invite_code
        from fastapi.responses import JSONResponse
        
        body = {"invite_code": "INVALID999"}
        
        with patch("api.routes.auth.require_user", return_value=user_id):
            result = await auth_redeem_invite_code(body, user_id)
        
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        assert "textinvalid" in result.body.decode()

    @pytest.mark.asyncio
    async def test_redeem_used_invite_code(self):
        """testtext"""
        await init_db()
        db = await get_main_db()
        
        user_id = await create_user("testuser3", "testpass", email="test3@example.com")
        
        # text
        await db.execute(
            """
            INSERT INTO invitation_codes (code, is_used, used_by_user_id, generated_at)
            VALUES (?, 1, 999, datetime('now'))
            """,
            ("USED999",),
        )
        await db.commit()
        
        from api.routes.auth import auth_redeem_invite_code
        from fastapi.responses import JSONResponse
        
        body = {"invite_code": "USED999"}
        
        with patch("api.routes.auth.require_user", return_value=user_id):
            result = await auth_redeem_invite_code(body, user_id)
        
        assert isinstance(result, JSONResponse)
        assert result.status_code == 409
        assert "text" in result.body.decode()


class TestQuotaManagement:
    """test API text"""

    @pytest.mark.asyncio
    async def test_init_user_api_quota(self):
        """testtext"""
        await init_db()
        user_id = await create_user("quotauser", "testpass", phone="13900139000")
        
        # text（default 5 text）
        await init_user_api_quota(user_id)
        
        quota = await get_user_api_quota(user_id)
        assert quota is not None
        assert quota["free_quota_remaining"] == 5
        assert quota["total_calls_made"] == 0
        
        # testtext（text）
        await init_user_api_quota(user_id)
        quota2 = await get_user_api_quota(user_id)
        assert quota2["free_quota_remaining"] == 5

    @pytest.mark.asyncio
    async def test_init_user_api_quota_custom_amount(self):
        """testtext（text）"""
        await init_db()
        user_id = await create_user("quotauser2", "testpass", email="quota@example.com")
        
        await init_user_api_quota(user_id, free_quota=50)
        
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 50

    @pytest.mark.asyncio
    async def test_get_user_api_quota_nonexistent(self):
        """testtextnot foundtext"""
        await init_db()
        
        quota = await get_user_api_quota(99999)
        assert quota is None

    @pytest.mark.asyncio
    async def test_consume_user_free_quota_success(self):
        """testtext"""
        await init_db()
        user_id = await create_user("consumeuser", "testpass", phone="13700137000")
        await init_user_api_quota(user_id, free_quota=5)
        
        # text 1 text
        success = await consume_user_free_quota(user_id, amount=1)
        assert success is True
        
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 4
        assert quota["total_calls_made"] == 1
        
        # text 2 text
        success2 = await consume_user_free_quota(user_id, amount=2)
        assert success2 is True
        
        quota2 = await get_user_api_quota(user_id)
        assert quota2["free_quota_remaining"] == 2
        assert quota2["total_calls_made"] == 2  # text：text +1

    @pytest.mark.asyncio
    async def test_consume_user_free_quota_insufficient(self):
        """testtext"""
        await init_db()
        user_id = await create_user("consumeuser2", "testpass", email="consume@example.com")
        await init_user_api_quota(user_id, free_quota=2)
        
        # text 1 text（text）
        success1 = await consume_user_free_quota(user_id, amount=1)
        assert success1 is True
        
        # text 1 text（text）
        success2 = await consume_user_free_quota(user_id, amount=1)
        assert success2 is True
        
        # text 1 text（text，text）
        success3 = await consume_user_free_quota(user_id, amount=1)
        assert success3 is False
        
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 0
        assert quota["total_calls_made"] == 2  # text

    @pytest.mark.asyncio
    async def test_consume_user_free_quota_atomic(self):
        """testtext"""
        await init_db()
        user_id = await create_user("atomicuser", "testpass", phone="13600136000")
        await init_user_api_quota(user_id, free_quota=1)
        
        # text 1 text（text）
        import asyncio
        
        async def consume():
            return await consume_user_free_quota(user_id, amount=1)
        
        results = await asyncio.gather(*[consume() for _ in range(5)])
        
        # text
        assert sum(results) == 1
        
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 0
        assert quota["total_calls_made"] == 1

    @pytest.mark.asyncio
    async def test_consume_user_free_quota_zero_amount(self):
        """testtext 0 text（text True，text）"""
        await init_db()
        user_id = await create_user("zerouser", "testpass", email="zero@example.com")
        await init_user_api_quota(user_id, free_quota=5)
        
        success = await consume_user_free_quota(user_id, amount=0)
        assert success is True
        
        quota = await get_user_api_quota(user_id)
        assert quota["free_quota_remaining"] == 5
        assert quota["total_calls_made"] == 0


class TestQuotaOwnerResolution:
    """testtext"""

    @pytest.mark.asyncio
    async def test_get_quota_owner_for_mac_with_owner(self):
        """testtext owner text user_id"""
        await init_db()
        db = await get_main_db()
        
        # text
        user_id = await create_user("owneruser", "testpass", phone="13500135000")
        
        # text（owner）
        mac = "AA:BB:CC:DD:EE:FF"
        await db.execute(
            """
            INSERT INTO device_memberships (mac, user_id, role, status, created_at, updated_at)
            VALUES (?, ?, 'owner', 'active', datetime('now'), datetime('now'))
            """,
            (mac, user_id),
        )
        await db.commit()
        
        owner_id = await get_quota_owner_for_mac(mac)
        assert owner_id == user_id

    @pytest.mark.asyncio
    async def test_get_quota_owner_for_mac_no_owner(self):
        """testtext owner text None"""
        await init_db()
        
        mac = "XX:XX:XX:XX:XX:XX"
        owner_id = await get_quota_owner_for_mac(mac)
        assert owner_id is None

    @pytest.mark.asyncio
    async def test_get_quota_owner_for_mac_member_only(self):
        """testtext member text owner text None"""
        await init_db()
        db = await get_main_db()
        
        user_id = await create_user("memberuser", "testpass", email="member@example.com")
        mac = "BB:CC:DD:EE:FF:AA"
        
        # text member，text owner
        await db.execute(
            """
            INSERT INTO device_memberships (mac, user_id, role, status, created_at, updated_at)
            VALUES (?, ?, 'member', 'active', datetime('now'), datetime('now'))
            """,
            (mac, user_id),
        )
        await db.commit()
        
        owner_id = await get_quota_owner_for_mac(mac)
        assert owner_id is None  # text get_device_owner text role='owner' text


class TestQuotaExhaustionHandling:
    """testtext"""

    @pytest.mark.asyncio
    async def test_quota_exhausted_returns_bmp_for_device(self):
        """testtext 1-bit BMP text"""
        await init_db()
        user_id = await create_user("exhaustuser", "testpass", phone="13400134000")
        await init_user_api_quota(user_id, free_quota=0)  # text 0
        
        # text（text mac text）
        from api.shared import build_image
        from unittest.mock import patch, AsyncMock
        
        # text get_quota_owner_for_mac text user_id
        with patch("api.shared.get_quota_owner_for_mac", return_value=user_id):
            # text LLM textmode（text DAILY）
            # text：text，text generate_and_render
            # text，texttest build_image text
            
            # text build_image text，texttesttext
            # texttesttexttesttext
            pass  # texttesttext test_integration.py

    @pytest.mark.asyncio
    async def test_quota_exhausted_returns_402_for_web_preview(self):
        """test Web text 402 text"""
        # texttesttext API texttesttext
        # text test_integration.py text API testtext
        pass


class TestLlmPrecheckBehavior:
    """testtext LLM text（text）。"""

    @pytest.mark.asyncio
    async def test_custom_mode_preview_quota_exhausted_blocks_llm(self, monkeypatch):
        """text custom preview text 0 text，text LLM text 402，text generate_json_mode_content。"""
        from api.routes.modes import custom_mode_preview

        # text
        monkeypatch.setenv("INKSIGHT_BILLING_ENABLED", "1")

        user_id = 123

        # text LLM textmode：content.type = "llm"
        body = {
            "mode_def": {
                "mode_id": "PREVIEW",
                "content": {
                    "type": "llm",
                    "prompt_template": "test {context}",
                },
            },
            "w": 400,
            "h": 300,
            "responseType": "json",
        }

        # text Key（text API key）
        async def fake_get_user_llm_config(_user_id: int):
            # text provider（text/text model），text
            return {
                "provider": "deepseek",
                "model": "",
                "api_key": "",
                "base_url": "",
                "image_provider": "aliyun",
                "image_api_key": "",
                "image_model": "qwen-image-plus",
            }

        # text 0
        async def fake_get_quota(user_id_param: int):
            assert user_id_param == user_id
            return {
                "user_id": user_id,
                "total_calls_made": 0,
                "free_quota_remaining": 0,
            }

        # text root text
        async def fake_get_role(user_id_param: int):
            assert user_id_param == user_id
            return "user"

        # LLM text，text
        called = {"generate": False}

        async def fake_generate_json_mode_content(*args, **kwargs):
            called["generate"] = True
            return {}

        from core import config_store as cfg_mod
        from core import json_content as json_mod
        from api import routes as api_pkg

        # text config_store text，text
        monkeypatch.setattr(cfg_mod, "get_user_llm_config", fake_get_user_llm_config)
        monkeypatch.setattr(cfg_mod, "get_user_api_quota", fake_get_quota)
        monkeypatch.setattr(cfg_mod, "get_user_role", fake_get_role)
        monkeypatch.setattr(json_mod, "generate_json_mode_content", fake_generate_json_mode_content)
        # text：text api.routes.modes text get_user_api_quota / get_user_role，
        # text DB text "no such table: api_quotas"
        monkeypatch.setattr("api.routes.modes.get_user_api_quota", fake_get_quota)
        monkeypatch.setattr("api.routes.modes.get_user_role", fake_get_role)

        # text admin_auth text None text
        resp = await custom_mode_preview(body, user_id=user_id)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 402
        assert "text" in resp.body.decode("utf-8")
        # text：LLM text
        assert called["generate"] is False

    @pytest.mark.asyncio
    async def test_generate_mode_quota_exhausted_blocks_llm(self, monkeypatch):
        """text AI textmodetext 0 text，text LLM text 402，text generate_mode_definition。"""
        from api.routes.modes import generate_mode

        monkeypatch.setenv("INKSIGHT_BILLING_ENABLED", "1")

        user_id = 456
        body = {
            "description": "texttestmodetext",
            "provider": "deepseek",
            "model": "deepseek-chat",
        }

        # text Key（text key）
        async def fake_get_user_llm_config(_user_id: int):
            # text user_llm_config text，text model text
            return {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key": "",
                "base_url": "",
                "image_provider": "aliyun",
                "image_api_key": "",
                "image_model": "qwen-image-plus",
            }

        async def fake_get_quota(user_id_param: int):
            assert user_id_param == user_id
            return {
                "user_id": user_id,
                "total_calls_made": 0,
                "free_quota_remaining": 0,
            }

        async def fake_get_role(user_id_param: int):
            assert user_id_param == user_id
            return "user"

        called = {"generate_mode": False}

        async def fake_generate_mode_definition(*args, **kwargs):
            called["generate_mode"] = True
            return {"ok": True, "mode_def": {}}

        from core import config_store as cfg_mod
        from core import mode_generator as mode_gen_mod

        # text API text，text api_quotas text
        monkeypatch.setattr(cfg_mod, "get_user_llm_config", fake_get_user_llm_config)
        monkeypatch.setattr(cfg_mod, "get_user_api_quota", fake_get_quota)
        monkeypatch.setattr(cfg_mod, "get_user_role", fake_get_role)
        monkeypatch.setattr(mode_gen_mod, "generate_mode_definition", fake_generate_mode_definition)
        monkeypatch.setattr("api.routes.modes.get_user_api_quota", fake_get_quota)
        monkeypatch.setattr("api.routes.modes.get_user_role", fake_get_role)

        resp = await generate_mode(body, user_id=user_id, admin_auth=None)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 402
        assert "text" in resp.body.decode("utf-8")
        # text：modetext LLM text
        assert called["generate_mode"] is False
