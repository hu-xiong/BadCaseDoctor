# -*- coding: utf-8 -*-
"""将 app.py 接上已拆出的 db_extensions / models 模块。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"

IMPORT_BLOCK = '''
from models.enums import (
    BadCaseStatus,
    BugStatus,
    CardType,
    ExecutionResult,
    ProposalStatus,
    TestCaseStatus,
)
from models.orm import (  # noqa: F401 — 保持 `from app import Bug` 等兼容
    AgentTask,
    BadCase,
    Bug,
    BugComment,
    Card,
    CardPlanRelation,
    CardTypeDefinition,
    ChatMessage,
    ChatSession,
    Comment,
    DiffReviewState,
    PaymentHistory,
    Plan,
    Project,
    ProjectPermission,
    PromptTemplate,
    Proposal,
    ProposalSnapshot,
    QuickCommand,
    ReactAgentRun,
    Team,
    TeamMember,
    TerminalAudit,
    TestCase,
    TestCaseComment,
    User,
    UserCredits,
    WorkflowInAppNotification,
    _append_badcase_comment_row,
    _append_bug_comment_row,
    _append_testcase_comment_row,
    _comment_author_name,
    _comment_parent_user_name_map,
    _comment_row_to_dict,
    _comments_detail_payload,
    _json_snowflake_id,
    _json_snowflake_ids_in_list,
    _persist_comment_from_queue_job,
    _submit_entity_comment_via_queue,
    _testcase_comments_detail_payload,
    _testcase_related_defects_detail_payload,
    _validate_comment_parent,
    ensure_badcase_card_link,
    repair_card_bug_source_if_missing,
    repair_card_source_link_if_missing,
)
'''

DB_INIT = '''from db_extensions import db
db.init_app(app)
''' + IMPORT_BLOCK


def main() -> None:
    lines = APP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    # 1) 枚举块 → 仅保留 EnumJSONEncoder 早期导入（app.json_encoder 需要）
    enum_import = "from models.enums import EnumJSONEncoder\n\n"
    start_enum = next(i for i, l in enumerate(lines) if l.startswith("class BugStatus"))
    end_enum = next(i for i, l in enumerate(lines) if l.strip() == "app = Flask(__name__)")
    lines = lines[:start_enum] + [enum_import] + lines[end_enum:]

    # 2) db = SQLAlchemy(app) → db_extensions + models 导入
    for i, line in enumerate(lines):
        if line.strip() == "db = SQLAlchemy(app)":
            lines[i : i + 1] = [DB_INIT]
            break
    else:
        raise RuntimeError("未找到 db = SQLAlchemy(app)")

    # 3) 去掉 ORM 实体块（原 844-2294，删枚举后约 799-2249）
    start = next(i for i, l in enumerate(lines) if l.strip() == "# 数据模型")
    end = next(
        i
        for i in range(start + 1, len(lines))
        if lines[i].startswith("@login_manager.user_loader")
    )
    lines = lines[:start] + lines[end:]

    # 4) 去掉 flask_sqlalchemy 直接 import（已由 db_extensions 提供）
    out: list[str] = []
    for line in lines:
        if line == "from flask_sqlalchemy import SQLAlchemy\n":
            continue
        out.append(line)

    APP_PATH.write_text("".join(out), encoding="utf-8")
    print(f"Patched {APP_PATH} — removed enums + ORM block, wired db_extensions/models")


if __name__ == "__main__":
    main()
