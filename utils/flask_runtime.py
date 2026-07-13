# -*- coding: utf-8 -*-
"""获取当前进程内唯一的 Flask app / db / ORM 模型（兼容 python app.py 的 __main__ 启动）。"""
from __future__ import annotations

import sys
from types import ModuleType
from typing import Any


def get_app_module() -> ModuleType:
    """
    python app.py 时路由与模型挂在 __main__；子模块若 from app import db 会再加载一份 app.py。
    优先 __main__，其次已加载的 app 模块。
    """
    for name in ("__main__", "app"):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        if getattr(mod, "db", None) is not None and getattr(mod, "Project", None) is not None:
            return mod
    import app as app_mod

    return app_mod


def get_db() -> Any:
    return get_app_module().db
