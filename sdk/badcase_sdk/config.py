# badcase_sdk/config.py
"""
SDK 配置：支持环境变量与显式 init
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SdkConfig:
    enabled: bool = True
    app: str = "unknown"
    env: str = "dev"

    @classmethod
    def from_env(cls) -> "SdkConfig":
        return cls(
            enabled=os.getenv("BADCASE_SDK_ENABLED", "true").lower() in ("1", "true", "yes"),
            app=os.getenv("BADCASE_SDK_APP", "unknown"),
            env=os.getenv("BADCASE_SDK_ENV", "dev"),
        )


_config: Optional[SdkConfig] = None


def init(app: Optional[str] = None, env: Optional[str] = None, enabled: Optional[bool] = None) -> None:
    """显式初始化配置"""
    global _config
    base = SdkConfig.from_env()
    _config = SdkConfig(
        enabled=base.enabled if enabled is None else enabled,
        app=app or base.app,
        env=env or base.env,
    )


def get_config() -> SdkConfig:
    """获取配置，未 init 时从环境变量加载"""
    global _config
    if _config is None:
        _config = SdkConfig.from_env()
    return _config
