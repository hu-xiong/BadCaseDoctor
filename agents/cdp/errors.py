# -*- coding: utf-8 -*-
"""CDP 工具错误码。"""

from __future__ import annotations


class CdpError(Exception):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        out = {
            "success": False,
            "error_code": self.code,
            "message": self.message,
        }
        out.update(self.extra)
        return out


STALE_REF = "stale_ref"
TIMEOUT = "timeout"
SESSION_NOT_FOUND = "session_not_found"
AMBIGUOUS_SELECTOR = "ambiguous_selector"
NAVIGATION_FAILED = "navigation_failed"
PLAYWRIGHT_UNAVAILABLE = "playwright_unavailable"
INVALID_ACTION = "invalid_action"
