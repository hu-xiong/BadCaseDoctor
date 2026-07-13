# -*- coding: utf-8 -*-
"""一次性脚本：从 app.py 拆出 models/enums.py、models/orm.py、db_extensions.py"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def main() -> None:
    lines = APP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    # enums: BugStatus .. ExecutionResult (1-based 133-177)
    enum_lines = lines[132:177]

    # ProposalStatus 嵌在 model 区段
    prop_start = next(i for i, l in enumerate(lines) if l.startswith("class ProposalStatus"))
    prop_end = next(
        i
        for i in range(prop_start + 1, len(lines))
        if lines[i].startswith("class ProposalSnapshot")
    )
    proposal_enum = lines[prop_start:prop_end]

    enums_header = '''"""ORM 状态枚举（自 app.py 拆出）。"""
from __future__ import annotations

import enum
import json
from datetime import datetime

'''
    enums_body = "".join(enum_lines) + "\n\n" + "".join(proposal_enum)
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "models" / "enums.py").write_text(enums_header + enums_body, encoding="utf-8")

    orm_header = '''"""SQLAlchemy ORM 实体（自 app.py 拆出；通过 app 模块 re-export）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import Enum, Text, and_, event, inspect, or_, text
from sqlalchemy.dialects.mysql import LONGTEXT

from db_extensions import db
from models.enums import (
    BadCaseStatus,
    BugStatus,
    CardType,
    ExecutionResult,
    ProposalStatus,
    TestCaseStatus,
)

'''
    orm_lines = []
    for i in range(843, 2294):
        if prop_start <= i < prop_end:
            continue
        orm_lines.append(lines[i])

    (ROOT / "models" / "orm.py").write_text(orm_header + "".join(orm_lines), encoding="utf-8")

    init_py = '''"""ORM 包：枚举 + 实体。"""
from models.enums import *  # noqa: F403
from models.orm import *  # noqa: F403
'''
    (ROOT / "models" / "__init__.py").write_text(init_py, encoding="utf-8")

    db_ext = '''"""Flask-SQLAlchemy 单例（与 app.py 共用，避免循环 import）。"""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
'''
    (ROOT / "db_extensions.py").write_text(db_ext, encoding="utf-8")

    print("Wrote models/enums.py, models/orm.py, models/__init__.py, db_extensions.py")


if __name__ == "__main__":
    main()
