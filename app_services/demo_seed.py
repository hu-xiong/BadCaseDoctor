# -*- coding: utf-8 -*-
"""SEED_DEMO_USERS=1 时种入演示账号、额度与示例项目。"""
from __future__ import annotations

import os
from typing import Any


def seed_demo_enabled() -> bool:
    return (os.getenv("SEED_DEMO_USERS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _free_credits() -> int:
    try:
        return max(0, int((os.getenv("AGENT_FREE_CREDITS_ON_FIRST_USE") or "50").strip() or "0"))
    except ValueError:
        return 50


def ensure_demo_credits_and_project(db: Any, user: Any, *, UserCredits: Any, Project: Any) -> None:
    """
    为演示用户确保有额度行与至少一个示例项目。
    不重置已有密码；不覆盖已有额度余额（仅在无额度行时创建）。
    """
    if user is None or getattr(user, "id", None) is None:
        return

    uid = int(user.id)
    credit = UserCredits.query.filter_by(user_id=uid).first()
    if not credit:
        n = _free_credits()
        db.session.add(
            UserCredits(user_id=uid, credits=n, total_purchased=0)
        )
        print(f"已为演示用户 {getattr(user, 'email', uid)} 种入额度 {n}")

    existing = (
        Project.query.filter_by(user_id=uid)
        .order_by(Project.id.asc())
        .first()
    )
    if existing:
        return

    proj = Project(
        name="演示项目",
        description="SEED_DEMO_USERS 自动创建的示例项目，可直接试用 Agent。",
        owner=getattr(user, "name", None) or "demo",
        status="published",
        user_id=uid,
        is_default=True,
    )
    db.session.add(proj)
    print(f"已为演示用户 {getattr(user, 'email', uid)} 创建示例项目「演示项目」")
