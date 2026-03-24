# badcase_sdk/flask_integration.py
"""
Flask 集成：install(app) 自动挂载 /metrics 端点
"""
from typing import Any, Optional

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


def install(
    app: Any,
    path: str = "/metrics",
    app_name: Optional[str] = None,
    env_name: Optional[str] = None,
) -> None:
    """
    挂载 Prometheus /metrics 端点到 Flask 应用
    可选：通过 app_name、env_name 覆盖默认配置
    """
    from .config import init

    if app_name is not None or env_name is not None:
        init(app=app_name, env=env_name)

    @app.route(path, methods=["GET"])
    def _metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
