import os

import pytest
from pydantic import HttpUrl, SecretStr

# 使用 autouse fixture 确保每次测试都有一个干净的环境来实例化 Settings 类。
# 否则，settings = Settings() 在 src/config.py 中会在导入时被实例化一次。


@pytest.fixture(scope="function", autouse=True)
def clean_env(monkeypatch):
    """
    确保环境干净，并返回一个可用的 Settings 类。
    我们必须在测试运行前清除所有可能影响 Settings 实例化的环境变量。
    """
    # 确定 src/config.py 模块是否存在并删除它，以便后续导入能重新运行 Settings() 实例化逻辑
    import sys

    if "src.config" in sys.modules:
        del sys.modules["src.config"]

    # 恢复常用的环境变量
    required_vars = [
        "VIKI_API_BASE",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT",
        "R2_BUCKET_NAME",
        "GEMINI_API_KEY",
        "WECHAT_APP_ID",
        "WECHAT_APP_SECRET",
        "ENV",
        "MODEL_CHAT",
        "MODEL_EMBEDDING",
        "UNSPLASH_ACCESS_KEY",
        "PEXELS_API_KEY",
        "PIXABAY_API_KEY",
        "WECHAT_PROXY_URL",
    ]

    original_env = {key: os.environ.get(key) for key in required_vars}

    for var in required_vars:
        if var in os.environ:
            monkeypatch.delenv(var)

    # 重新导入 Settings 类
    from src.config import Settings

    yield Settings

    # 恢复环境变量
    for key, value in original_env.items():
        if value is not None:
            monkeypatch.setenv(key, value)
        elif key in os.environ:
            monkeypatch.delenv(key)


def get_minimal_env_vars():
    """提供实例化 Settings 所需的最小环境变量字典。"""
    return {
        "VIKI_API_BASE": "https://viki.moe",
        "R2_ACCOUNT_ID": "acc_id",
        "R2_ACCESS_KEY_ID": "key_id",
        "R2_SECRET_ACCESS_KEY": "secret_key",
        "R2_ENDPOINT": "https://r2.endpoint.com",
        "R2_BUCKET_NAME": "bucket_name",
        "GEMINI_API_KEY": "gemini_key",
        "WECHAT_APP_ID": "wx_id",
        "WECHAT_APP_SECRET": "wx_secret",
    }


def test_config_required_fields_check(clean_env, monkeypatch):
    """测试缺少必填环境变量时 Settings 无法实例化。"""
    Settings = clean_env
    # 故意不设置任何必填变量
    with pytest.raises(Exception) as excinfo:
        Settings()

    error_message = str(excinfo.value)
    assert "VIKI_API_BASE" in error_message
    assert "R2_ACCOUNT_ID" in error_message


def test_config_loads_from_env(clean_env, monkeypatch):
    """测试所有必填字段都能正确从环境变量加载。"""
    Settings = clean_env

    # 模拟所有必填环境变量
    for key, value in get_minimal_env_vars().items():
        monkeypatch.setenv(key, value)

    # 模拟可选/默认环境变量
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("MODEL_CHAT", "gemini-test-model")

    # 实例化应该成功
    settings = Settings()

    # 检查值和类型
    assert settings.ENV == "production"
    assert settings.VIKI_API_BASE == HttpUrl("https://viki.moe")
    assert settings.R2_SECRET_ACCESS_KEY == SecretStr("secret_key")
    assert settings.WECHAT_PROXY_URL == "socks5://redate-proxy:1080"  # 检查默认值
    assert settings.MODEL_CHAT == "gemini-test-model"

    # 检查不可变性 (frozen=True)
    with pytest.raises(TypeError):
        # noinspection PyPropertyAccess
        settings.R2_ACCOUNT_ID = "new_id"


def test_wechat_proxy_url_override(clean_env, monkeypatch):
    """测试 WECHAT_PROXY_URL 可以被覆盖。"""
    Settings = clean_env

    # 模拟必填环境变量
    for key, value in get_minimal_env_vars().items():
        monkeypatch.setenv(key, value)

    # 覆盖默认代理
    new_proxy = "http://127.0.0.1:8080"
    monkeypatch.setenv("WECHAT_PROXY_URL", new_proxy)

    settings = Settings()
    assert settings.WECHAT_PROXY_URL == new_proxy
