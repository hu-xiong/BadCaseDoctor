# -*- coding: utf-8 -*-
"""CDP 浏览器自动化核心。"""

from .session_manager import CdpSessionManager
from .settings import cdp_enabled

__all__ = ["CdpSessionManager", "cdp_enabled"]
