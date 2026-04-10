"""
testtextmodetext API key text（text，text）

testtext：
1. _get_client text api_key
2. _get_client text None
3. pipeline.py text api_key
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.errors import LLMKeyMissingError
from core.content import _get_client
from core.crypto import encrypt_api_key, decrypt_api_key


class TestGetClientApiKeyLogic:
    """test _get_client text api_key text"""

    def test_get_client_uses_user_api_key(self):
        """test _get_client text api_key"""
        user_api_key = "sk-user-key-12345"
        
        # text client，text
        client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=user_api_key)
        
        assert client is not None
        assert max_tokens > 0

    def test_get_client_uses_env_var_when_api_key_is_none(self):
        """test _get_client text api_key text None text"""
        env_api_key = "sk-env-key-67890"
        
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}, clear=False):
            client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=None)
            
            assert client is not None
            assert max_tokens > 0

    def test_get_client_raises_error_when_user_key_empty(self):
        """test _get_client text api_key text"""
        with (
            patch.dict(os.environ, {}, clear=True),  # text
        ):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key="")
            
            # text"text"
            assert "text" in str(exc_info.value)

    def test_get_client_raises_error_when_no_key_at_all(self):
        """test _get_client text api_key text"""
        with (
            patch.dict(os.environ, {}, clear=True),  # text
        ):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key=None)
            
            # text"text"（text）
            assert "text" not in str(exc_info.value)

    def test_get_client_distinguishes_user_key_from_env_key(self):
        """test _get_client text api_key text"""
        user_api_key = "sk-user-key-12345"
        env_api_key = "sk-env-key-67890"
        
        # test1: text api_key，text
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}, clear=False):
            client1, _ = _get_client("deepseek", "deepseek-chat", api_key=user_api_key)
            assert client1 is not None
        
        # test2: text，text
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}, clear=False):
            client2, _ = _get_client("deepseek", "deepseek-chat", api_key=None)
            assert client2 is not None
        
        # test3: text，text（text）
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}, clear=False):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key="")
            assert "text" in str(exc_info.value)


class TestPipelineApiKeyDecryption:
    """test pipeline.py text api_key text"""

    def test_pipeline_decrypts_valid_api_key(self):
        """test pipeline text api_key"""
        user_api_key = "sk-user-key-12345"
        encrypted_key = encrypt_api_key(user_api_key)
        
        # text pipeline.py text
        from core.crypto import decrypt_api_key
        decrypted = decrypt_api_key(encrypted_key)
        
        assert decrypted == user_api_key
        assert decrypted and decrypted.strip()  # text

    def test_pipeline_handles_decryption_failure(self):
        """test pipeline text"""
        # text（text）
        invalid_encrypted = "invalid-encrypted-key"
        
        from core.crypto import decrypt_api_key
        decrypted = decrypt_api_key(invalid_encrypted)
        
        # text
        assert decrypted == ""
        
        # text pipeline.py text
        device_api_key = decrypted if decrypted and decrypted.strip() else ""
        assert device_api_key == ""  # text

    def test_pipeline_handles_empty_encrypted_key(self):
        """test pipeline text key text"""
        # text
        encrypted_key = ""
        
        # text pipeline.py text
        device_api_key = None
        if encrypted_key:
            from core.crypto import decrypt_api_key
            decrypted = decrypt_api_key(encrypted_key)
            device_api_key = decrypted if decrypted and decrypted.strip() else ""
        
        assert device_api_key is None  # text None


class TestApiKeyFlow:
    """testtext api_key text"""

    def test_user_key_flow(self):
        """testtext api_key text"""
        user_api_key = "sk-user-key-12345"
        
        # 1. text
        encrypted = encrypt_api_key(user_api_key)
        assert encrypted != user_api_key
        assert encrypted != ""
        
        # 2. text
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == user_api_key
        
        # 3. text _get_client
        client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=decrypted)
        assert client is not None
        assert max_tokens > 0

    def test_empty_key_flow(self):
        """testtext api_key text"""
        # 1. text
        encrypted = encrypt_api_key("")
        # text
        assert encrypted == ""
        
        # 2. text
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""
        
        # 3. text _get_client text
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(LLMKeyMissingError) as exc_info:
                _get_client("deepseek", "deepseek-chat", api_key=decrypted)
            assert "text" in str(exc_info.value)

    def test_none_key_flow(self):
        """test None api_key text"""
        # 1. text，device_api_key text None
        device_api_key = None
        
        # 2. text _get_client，text
        env_api_key = "sk-env-key-67890"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": env_api_key}, clear=False):
            client, max_tokens = _get_client("deepseek", "deepseek-chat", api_key=device_api_key)
            assert client is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
