"""
app_services/db_schema.py
"""
from __future__ import annotations

import os

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from db_extensions import db


def _adapt_create_table_columns_for_dialect(columns):
    """CREATE TABLE 列定义：SQLite 用 AUTOINCREMENT，MySQL 用 AUTO_INCREMENT。"""
    dialect = (db.engine.dialect.name or "").lower()
    if dialect != "mysql":
        return columns
    return [
        c.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY AUTO_INCREMENT")
        .replace("AUTOINCREMENT", "AUTO_INCREMENT")
        for c in columns
    ]


def drop_mysql_foreign_key_constraints():
    """MySQL：移除库内所有外键（项目约定不使用 DB 级外键，引用由应用层维护）。"""
    if (db.engine.dialect.name or "").lower() != "mysql":
        return
    try:
        rows = db.session.execute(
            text(
                """
                SELECT TABLE_NAME, CONSTRAINT_NAME
                FROM information_schema.TABLE_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND CONSTRAINT_TYPE = 'FOREIGN KEY'
                """
            )
        ).fetchall()
        if not rows:
            return
        dropped = 0
        for table_name, constraint_name in rows:
            try:
                db.session.execute(
                    text(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint_name}`")
                )
                dropped += 1
                print(f"[DB] 已移除外键 {table_name}.{constraint_name}", flush=True)
            except Exception as ex:
                db.session.rollback()
                print(f"[DB] 移除外键失败 {table_name}.{constraint_name}: {ex}", flush=True)
        db.session.commit()
        if dropped:
            print(f"[DB] 共移除 {dropped} 个外键约束", flush=True)
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[DB] 扫描/移除外键失败: {e}", flush=True)


def sync_database_schema():
    """同步数据库表结构，确保与代码中的模型完全一致"""
    try:
        print("开始同步数据库表结构...")
        
        # 获取数据库检查器
        inspector = inspect(db.engine)

        # === 兼容迁移：bad_case 字段重命名（避免 answer/correct_answer 混淆） ===
        # correct_answer      -> answer
        # correct_answer_final-> correct_answer
        def _migrate_bad_case_answer_fields():
            try:
                cols = inspector.get_columns('bad_case')
                col_names = {c.get('name') for c in (cols or [])}
                # 先把 correct_answer 重命名为 answer
                if 'correct_answer' in col_names and 'answer' not in col_names:
                    print("[DB] 迁移: bad_case.correct_answer -> bad_case.answer")
                    db.session.execute(text('ALTER TABLE bad_case RENAME COLUMN correct_answer TO answer'))
                    db.session.commit()
                    cols = inspector.get_columns('bad_case')
                    col_names = {c.get('name') for c in (cols or [])}
                # 再把 correct_answer_final 重命名为 correct_answer
                if 'correct_answer_final' in col_names and 'correct_answer' not in col_names:
                    print("[DB] 迁移: bad_case.correct_answer_final -> bad_case.correct_answer")
                    db.session.execute(text('ALTER TABLE bad_case RENAME COLUMN correct_answer_final TO correct_answer'))
                    db.session.commit()
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[DB] ⚠️ bad_case 字段迁移失败(可忽略/手动处理): {e}")

        def _migrate_bug_plan_id_nullable():
            """历史库 bug.plan_id 常为 NOT NULL，与 ORM Bug.plan_id nullable=True /「未计划 Bug」不一致，会导致 plan_id=NULL 插入失败。"""
            try:
                insp = inspect(db.engine)
                if not insp.has_table('bug'):
                    return
                cols = insp.get_columns('bug')
                plan_col = next((c for c in cols if c.get('name') == 'plan_id'), None)
                if not plan_col:
                    return
                if plan_col.get('nullable', True):
                    return
                dialect = (db.engine.dialect.name or '').lower()
                if dialect == 'mysql':
                    print("[DB] 迁移: bug.plan_id 允许 NULL（未计划 Bug / create 预览 plan_id 为空）")
                    db.session.execute(text('ALTER TABLE bug MODIFY COLUMN plan_id BIGINT NULL'))
                    db.session.commit()
                elif dialect in ('postgresql', 'postgres'):
                    db.session.execute(text('ALTER TABLE bug ALTER COLUMN plan_id DROP NOT NULL'))
                    db.session.commit()
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[DB] ⚠️ bug.plan_id 可空迁移失败(可手动执行 ALTER): {e}")

        _migrate_bad_case_answer_fields()
        _migrate_bug_plan_id_nullable()

        def _migrate_bug_drop_description_column():
            """复现步骤仅保留 steps_to_reproduce；合并 description 遗留数据后删列。"""
            try:
                insp = inspect(db.engine)
                if not insp.has_table('bug'):
                    return
                cols = {c.get('name') for c in (insp.get_columns('bug') or [])}
                if 'description' not in cols:
                    return
                dialect = (db.engine.dialect.name or '').lower()
                print("[DB] 迁移: bug.description -> steps_to_reproduce 后删除 description 列")
                if dialect == 'mysql':
                    db.session.execute(
                        text(
                            "UPDATE bug SET steps_to_reproduce = description "
                            "WHERE (steps_to_reproduce IS NULL OR TRIM(steps_to_reproduce) = '') "
                            "AND description IS NOT NULL AND TRIM(description) <> ''"
                        )
                    )
                    db.session.execute(text('ALTER TABLE bug DROP COLUMN description'))
                elif dialect in ('postgresql', 'postgres'):
                    db.session.execute(
                        text(
                            "UPDATE bug SET steps_to_reproduce = description "
                            "WHERE (steps_to_reproduce IS NULL OR BTRIM(steps_to_reproduce) = '') "
                            "AND description IS NOT NULL AND BTRIM(description) <> ''"
                        )
                    )
                    db.session.execute(text('ALTER TABLE bug DROP COLUMN description'))
                else:
                    db.session.execute(
                        text(
                            "UPDATE bug SET steps_to_reproduce = description "
                            "WHERE (steps_to_reproduce IS NULL OR TRIM(steps_to_reproduce) = '') "
                            "AND description IS NOT NULL AND TRIM(description) <> ''"
                        )
                    )
                    db.session.execute(text('ALTER TABLE bug DROP COLUMN description'))
                db.session.commit()
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[DB] ⚠️ bug.description 列迁移失败(可手动处理): {e}")

        _migrate_bug_drop_description_column()

        def _migrate_badcase_testcase_card_id_columns():
            """bad_case / test_case 增加 card_id，并从已有 Card.source_type/source_id 回填。"""
            try:

                def _ensure_col(table: str) -> None:
                    ins = inspect(db.engine)
                    if not ins.has_table(table):
                        return
                    cols = {c.get("name") for c in (ins.get_columns(table) or [])}
                    if "card_id" in cols:
                        return
                    dialect = (db.engine.dialect.name or "").lower()
                    print(f"[DB] 迁移: {table}.card_id 可空 BIGINT（雪花/跨表 id）")
                    if dialect == "mysql":
                        db.session.execute(
                            text(f"ALTER TABLE {table} ADD COLUMN card_id BIGINT NULL")
                        )
                    else:
                        db.session.execute(
                            text(f"ALTER TABLE {table} ADD COLUMN card_id INTEGER")
                        )
                    db.session.commit()

                _ensure_col("bad_case")
                _ensure_col("test_case")

                # 从 Card 映射回填源表 card_id（老数据仅有 source_* 时）
                if inspect(db.engine).has_table("bad_case") and inspect(
                    db.engine
                ).has_table("card"):
                    qcards = (
                        Card.query.filter(
                            Card.type == CardType.BADCASE,
                            or_(
                                Card.source_type == "badcase",
                                Card.source_type == "bad_case",
                            ),
                            Card.source_id.isnot(None),
                        )
                        .all()
                    )
                    nbc = 0
                    for c in qcards:
                        try:
                            bid = int(c.source_id)
                        except (TypeError, ValueError):
                            continue
                        bc = BadCase.query.get(bid)
                        if (
                            bc
                            and int(bc.project_id) == int(c.project_id)
                            and (getattr(bc, "card_id", None) in (None, 0))
                        ):
                            bc.card_id = int(c.id)
                            nbc += 1
                    if nbc:
                        db.session.commit()
                        print(f"[DB] 回填 bad_case.card_id 自 Card: {nbc} 条", flush=True)

                if inspect(db.engine).has_table("test_case") and inspect(
                    db.engine
                ).has_table("card"):
                    qcards = (
                        Card.query.filter(
                            Card.type == CardType.TESTCASE,
                            or_(
                                Card.source_type == "testcase",
                                Card.source_type == "test_case",
                            ),
                            Card.source_id.isnot(None),
                        )
                        .all()
                    )
                    ntc = 0
                    for c in qcards:
                        try:
                            tid = int(c.source_id)
                        except (TypeError, ValueError):
                            continue
                        tc = TestCase.query.get(tid)
                        if (
                            tc
                            and int(tc.project_id) == int(c.project_id)
                            and (getattr(tc, "card_id", None) in (None, 0))
                        ):
                            tc.card_id = int(c.id)
                            ntc += 1
                    if ntc:
                        db.session.commit()
                        print(f"[DB] 回填 test_case.card_id 自 Card: {ntc} 条", flush=True)
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(
                    f"[DB] ⚠️ bad_case/test_case card_id 迁移失败(可手动 ALTER): {e}",
                    flush=True,
                )

        _migrate_badcase_testcase_card_id_columns()

        def _migrate_mysql_entity_ids_bigint_for_snowflake():
            """MySQL：将 Bug/Card/BadCase/TestCase/Plan 主键及引用列扩为 BIGINT，便于雪花 id。需 SNOWFLAKE_ENTITY_PK_MIGRATE=1。"""
            if (db.engine.dialect.name or "").lower() != "mysql":
                return
            if (os.getenv("SNOWFLAKE_ENTITY_PK_MIGRATE") or "").strip() != "1":
                return
            stmts = [
                "ALTER TABLE bug MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE test_case MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE card MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE card_plan_relation MODIFY COLUMN plan_id BIGINT NOT NULL",
                "ALTER TABLE diff_review_state MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE bug MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE test_case MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE card MODIFY COLUMN source_id BIGINT NULL",
                "ALTER TABLE comment MODIFY COLUMN badcase_id BIGINT NOT NULL",
                "ALTER TABLE bug_comment MODIFY COLUMN bug_id BIGINT NOT NULL",
                "ALTER TABLE card_plan_relation MODIFY COLUMN card_id BIGINT NOT NULL",
                "ALTER TABLE diff_review_state MODIFY COLUMN target_id BIGINT NOT NULL",
                "ALTER TABLE workflow_in_app_notification MODIFY COLUMN entity_id BIGINT NOT NULL",
                "ALTER TABLE bug MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE test_case MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE card MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE plan MODIFY COLUMN parent_id BIGINT NULL",
                "ALTER TABLE plan MODIFY COLUMN id BIGINT NOT NULL",
            ]
            for sql in stmts:
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"[DB] 雪花列迁移 OK: {sql}", flush=True)
                except Exception as ex:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    print(f"[DB] 雪花列迁移跳过: {sql} ({ex})", flush=True)

        _migrate_mysql_entity_ids_bigint_for_snowflake()

        def _warn_mysql_int_entity_pk_if_needed():
            if (db.engine.dialect.name or "").lower() != "mysql":
                return
            if (os.getenv("SNOWFLAKE_ENTITY_PK_MIGRATE") or "").strip() == "1":
                return
            try:
                insp = inspect(db.engine)
                if not insp.has_table("bug"):
                    return
                for c in insp.get_columns("bug") or []:
                    if c.get("name") != "id":
                        continue
                    t = c.get("type")
                    tn = (getattr(t, "__visit_name__", None) or str(t)).lower()
                    if "bigint" in tn:
                        return
                    print(
                        "[DB] 提示：Bug/Card/Plan 等主键已改为应用层雪花；MySQL 表 bug.id 等仍为整型时，"
                        "请先设环境变量 SNOWFLAKE_ENTITY_PK_MIGRATE=1 启动一次以执行 ALTER 扩 BIGINT，"
                        "否则新插入雪花 id 会失败。",
                        flush=True,
                    )
                    break
            except Exception:
                pass

        _warn_mysql_int_entity_pk_if_needed()

        # 重要：SQLite ALTER TABLE 后 inspector 可能缓存旧列信息，重新创建 inspector 避免重复加列
        inspector = inspect(db.engine)
        
        # 定义表结构映射
        table_definitions = {
            'user': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'email VARCHAR(120) UNIQUE NOT NULL',
                    'password_hash VARCHAR(200) NOT NULL',
                    'name VARCHAR(100) NOT NULL',
                    'role VARCHAR(20) DEFAULT "collaborator"',
                    'is_verified BOOLEAN DEFAULT FALSE',
                    'verification_code VARCHAR(10)',
                    'verification_expires DATETIME',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP'
                ]
            },
            'project': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'description TEXT',
                    'avatar VARCHAR(500)',
                    'owner VARCHAR(100)',
                    'intro TEXT',
                    'status VARCHAR(20) DEFAULT "published"',
                    # 与 ORM Project.login_configs 对齐；缺列时由上方向现有表 ADD COLUMN
                    'login_configs TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'user_id INT NOT NULL',
                    'is_default BOOLEAN DEFAULT FALSE',
                    'cloned_from_template_id INT',
                ]
            },
            'project_permission': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'project_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'role VARCHAR(20) NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'bad_case': {
                'columns': [
                    'id BIGINT PRIMARY KEY',
                    'project_id INT NOT NULL',
                    'plan_id BIGINT',
                    'creator_id INT NOT NULL',
                    'title VARCHAR(200)',
                    'case_category VARCHAR(100) NOT NULL',
                    'base_problem TEXT NOT NULL',
                    'reproduction_steps TEXT',
                    'badcase_result TEXT NOT NULL',
                    'answer TEXT NOT NULL',
                    'correct_answer TEXT',
                    'problem_reason TEXT',
                    'needs_processing BOOLEAN DEFAULT TRUE',
                    'solution TEXT',
                    'is_verified BOOLEAN DEFAULT FALSE',
                    'priority VARCHAR(10) DEFAULT "p3"',
                    'status VARCHAR(20) DEFAULT "new"',
                    'assignee VARCHAR(100)',
                    'plan VARCHAR(100)',
                    'document_type VARCHAR(100)',
                    'attachments TEXT',
                    'assigned_users TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'badcase_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'prompt_template': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'content TEXT NOT NULL',
                    'project_id INT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'team': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'description TEXT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'team_member': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'team_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'role VARCHAR(20) DEFAULT "member"',
                    'permissions TEXT',
                    'joined_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'plan': {
                'columns': [
                    'id BIGINT PRIMARY KEY',
                    'name VARCHAR(200) NOT NULL',
                    'description TEXT',
                    'status VARCHAR(20) DEFAULT "active"',
                    'priority VARCHAR(10) DEFAULT "medium"',
                    'is_pinned BOOLEAN DEFAULT FALSE',
                    'start_date DATE',
                    'end_date DATE',
                    'progress FLOAT DEFAULT 0.0',
                    'parent_id BIGINT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'assignee_id INT',
                    'scope_notification BOOLEAN DEFAULT FALSE',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'bug': {
                'columns': [
                    'id BIGINT PRIMARY KEY',
                    'title VARCHAR(200) NOT NULL',
                    'steps_to_reproduce TEXT',
                    'expected_result TEXT',
                    'actual_result TEXT',
                    'severity VARCHAR(20) DEFAULT "medium"',
                    'priority VARCHAR(10) DEFAULT "p3"',
                    'status VARCHAR(20) DEFAULT "new"',
                    'bug_type VARCHAR(50)',
                    'environment VARCHAR(100)',
                    'browser VARCHAR(50)',
                    'os VARCHAR(50)',
                    'plan_id BIGINT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'assignee_id INT',
                    'attachments TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'bug_comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'bug_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'test_case_comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'test_case_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'test_case': {
                'columns': [
                    'id BIGINT PRIMARY KEY',
                    'title VARCHAR(200) NOT NULL',
                    'status VARCHAR(20) DEFAULT "draft"',
                    'case_type VARCHAR(50) DEFAULT "功能测试"',
                    'priority VARCHAR(10) DEFAULT "P3"',
                    'test_type VARCHAR(20) DEFAULT "手动"',
                    'preconditions TEXT',
                    'steps TEXT',
                    'remark TEXT',
                    'requirement_id INT',
                    'related_defects TEXT',
                    'baseline VARCHAR(100)',
                    'estimated_time INT DEFAULT 0',
                    'actual_time INT',
                    'remaining_time INT',
                    'last_executed DATETIME',
                    'executed_by INT',
                    'execution_result VARCHAR(20)',
                    'version VARCHAR(20) DEFAULT "v1"',
                    'plan_id BIGINT',
                    'project_id INT NOT NULL',
                    'creator_id INT',
                    'assignee_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'workflow_in_app_notification': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTO_INCREMENT',
                    'user_id INT NOT NULL',
                    'actor_id INT',
                    'actor_name VARCHAR(120)',
                    'event VARCHAR(40) NOT NULL',
                    'entity_type VARCHAR(20) NOT NULL',
                    'entity_id BIGINT NOT NULL',
                    'title VARCHAR(500)',
                    'project_id INT',
                    'project_name VARCHAR(200)',
                    'status VARCHAR(64)',
                    'previous_status VARCHAR(64)',
                    'search_blob TEXT',
                    'read_at DATETIME',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'chat_session': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'title VARCHAR(200) NOT NULL',
                    'project_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'is_active BOOLEAN DEFAULT 1',
                    'memory_enabled BOOLEAN DEFAULT 1',
                    'memory_data TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'chat_message': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'session_id INT NOT NULL',
                    'user_id INT',
                    'is_user BOOLEAN DEFAULT 1',
                    'content TEXT NOT NULL',
                    'understanding TEXT',
                    'reasoning TEXT',
                    'steps TEXT',
                    'execution_results TEXT',
                    'agent_result TEXT',
                    'evidences TEXT',
                    'navigation TEXT',
                    'modify_navigation TEXT',
                    'modify_groups TEXT',
                    'delete_navigation TEXT',
                    'final_response TEXT',
                    'llm_model VARCHAR(128)',
                    'images LONGTEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'diff_review_state': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'project_id INT NOT NULL',
                    'target VARCHAR(32) NOT NULL',
                    'target_id BIGINT NOT NULL',
                    'plan_id BIGINT',
                    'lifecycle_id INT DEFAULT 1',
                    'diff_fingerprint VARCHAR(64) DEFAULT ""',
                    'status VARCHAR(20) DEFAULT "pending"',
                    'diff_payload TEXT',
                    'modifications_payload TEXT',
                    'source_message_id INT',
                    'source_session_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'adopted_at DATETIME',
                    'rejected_at DATETIME',
                    'operator_id INT',
                ]
            },
            'agent_tasks': {
                'columns': [
                    'id VARCHAR(36) PRIMARY KEY',
                    'name VARCHAR(100) NOT NULL',
                    'status VARCHAR(20) NOT NULL DEFAULT "pending"',
                    'params TEXT',
                    'result TEXT',
                    'error TEXT',
                    'dependencies TEXT',
                    'session_id VARCHAR(64)',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'started_at DATETIME',
                    'finished_at DATETIME',
                ]
            },
            'react_agent_runs': {
                'columns': [
                    'id VARCHAR(36) PRIMARY KEY',
                    'chat_session_id INT NOT NULL',
                    'project_id INT',
                    'user_id INT NOT NULL',
                    'react_request_id VARCHAR(64) NOT NULL',
                    'status VARCHAR(20) NOT NULL DEFAULT "interrupted"',
                    'user_input TEXT',
                    'model_name VARCHAR(128)',
                    'checkpoint_json TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
            'cdp_test_runs': {
                'columns': [
                    'id VARCHAR(36) PRIMARY KEY',
                    'chat_session_id INT',
                    'react_request_id VARCHAR(64)',
                    'project_id INT NOT NULL',
                    'plan_id BIGINT',
                    'user_id INT NOT NULL',
                    'mode VARCHAR(32) NOT NULL DEFAULT "manual"',
                    'title VARCHAR(200) NOT NULL DEFAULT "CDP 测试"',
                    'status VARCHAR(20) NOT NULL DEFAULT "running"',
                    'spec_json TEXT',
                    'steps_json TEXT',
                    'summary TEXT',
                    'pass_count INT DEFAULT 0',
                    'fail_count INT DEFAULT 0',
                    'cdp_session_id VARCHAR(64)',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'finished_at DATETIME',
                ]
            },
            'terminal_audit': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTO_INCREMENT',
                    'user_id INT NOT NULL',
                    'project_id INT',
                    'event_type VARCHAR(40) NOT NULL',
                    'client_session_id VARCHAR(64)',
                    'detail TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                ]
            },
        }
        
        # 检查并创建/更新每个表
        for table_name, definition in table_definitions.items():
            # 检查表是否存在
            table_exists = inspector.has_table(table_name)
            
            if not table_exists:
                # 创建新表
                cols = _adapt_create_table_columns_for_dialect(definition["columns"])
                create_sql = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(cols) + "\n)"
                db.session.execute(text(create_sql))
                print(f"已创建表: {table_name}")
            else:
                # 检查现有表的列
                existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                required_columns = []
                
                # 解析需要的列
                for col_def in definition['columns']:
                    if 'FOREIGN KEY' not in col_def and 'PRIMARY KEY' not in col_def:
                        col_name = col_def.split()[0]
                        if col_name not in existing_columns:
                            required_columns.append(col_def)
                
                # 添加缺失的列
                for col_def in required_columns:
                    col_name = col_def.split()[0]
                    if col_name not in existing_columns:
                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_def}"
                        db.session.execute(text(alter_sql))
                        print(f"已添加列 {table_name}.{col_name}")
        
        db.session.commit()
        print("数据库表结构同步完成")

        drop_mysql_foreign_key_constraints()
        
        # 先清理 diff_review_state 历史脏数据（同记录多条状态），再建索引
        cleanup_diff_review_duplicates()
        # 旧数据 operator_id 为空时回填为指定用户（默认 id=33）
        backfill_diff_review_legacy_operator(33)

        # 创建性能优化索引
        create_performance_indexes()

        reset_agent_tasks_stuck_running()
        
        # 演示账号仅显式开启时种入（SEED_DEMO_USERS=1），生产默认跳过且绝不重置密码
        _seed_demo = (os.getenv("SEED_DEMO_USERS") or "").strip().lower() in (
            "1", "true", "yes", "on"
        )
        if _seed_demo:
            test_user = User.query.filter_by(email='test@example.com').first()
            if not test_user:
                test_user = User(
                    email='test@example.com',
                    password_hash=generate_password_hash('123456'),
                    name='测试用户',
                    is_verified=True
                )
                db.session.add(test_user)
                print("已创建测试用户: test@example.com / 123456")

            specified_user = User.query.filter_by(email='2629258027@qq.com').first()
            if not specified_user:
                specified_user = User(
                    email='2629258027@qq.com',
                    password_hash=generate_password_hash('123456'),
                    name='hx',
                    is_verified=True
                )
                db.session.add(specified_user)
                print("已创建指定用户: 2629258027@qq.com / 123456")
            else:
                print("演示用户已存在，跳过密码重置: 2629258027@qq.com")
        else:
            print("跳过演示账号种入（设 SEED_DEMO_USERS=1 开启）")
        
        db.session.commit()
        
        return True
        
    except Exception as e:
        print(f"数据库同步过程中出现错误: {e}")
        db.session.rollback()
        return False

def reset_agent_tasks_stuck_running():
    """进程重启后：将 agent_tasks 中 running 重置为 pending，便于调度器重新领取（需求 6.5）。"""
    try:
        if not inspect(db.engine).has_table('agent_tasks'):
            return
        n = (
            AgentTask.query.filter(AgentTask.status == 'running')
            .update(
                {'status': 'pending', 'started_at': None},
                synchronize_session=False,
            )
        )
        if n:
            db.session.commit()
            print(f"[AGENT_TASK] 已将 {n} 条 running 任务重置为 pending")
        else:
            db.session.commit()
    except Exception as e:
        print(f"[AGENT_TASK] running→pending 重置失败: {e}")
        db.session.rollback()


def cleanup_diff_review_duplicates():
    """清理 diff_review_state 脏数据：同 (project_id,target,target_id) 仅保留最新一条。"""
    try:
        if not inspect(db.engine).has_table('diff_review_state'):
            return
        rows = (
            DiffReviewState.query
            .order_by(
                DiffReviewState.project_id.asc(),
                DiffReviewState.target.asc(),
                DiffReviewState.target_id.asc(),
                DiffReviewState.updated_at.desc(),
                DiffReviewState.id.desc(),
            )
            .all()
        )
        keep_keys = set()
        delete_ids = []
        for r in rows:
            k = (r.project_id, r.target, r.target_id)
            if k in keep_keys:
                delete_ids.append(r.id)
            else:
                keep_keys.add(k)
        if delete_ids:
            DiffReviewState.query.filter(DiffReviewState.id.in_(delete_ids)).delete(synchronize_session=False)
            db.session.commit()
            print(f"[DIFF-CLEANUP] 已删除重复状态行: {len(delete_ids)}")
        else:
            print("[DIFF-CLEANUP] 无重复状态行")
    except Exception as e:
        print(f"[DIFF-CLEANUP] 清理失败: {e}")
        db.session.rollback()


def backfill_diff_review_legacy_operator(default_user_id=33):
    """历史 diff_review_state.operator_id 为 NULL 时回填为指定用户 id（默认 33）。"""
    try:
        if not inspect(db.engine).has_table('diff_review_state'):
            return
        cols = [c['name'] for c in inspect(db.engine).get_columns('diff_review_state')]
        if 'operator_id' not in cols:
            return
        if db.session.get(User, default_user_id) is None:
            print(f"[DIFF-BACKFILL] 用户 id={default_user_id} 不存在，跳过 operator_id 回填")
            return
        res = db.session.execute(
            text('UPDATE diff_review_state SET operator_id = :uid WHERE operator_id IS NULL'),
            {'uid': default_user_id},
        )
        db.session.commit()
        n = getattr(res, 'rowcount', None)
        if n is not None and n > 0:
            print(f'[DIFF-BACKFILL] 已将 {n} 条 operator_id 为空的记录回填为 user_id={default_user_id}')
    except Exception as e:
        db.session.rollback()
        print(f'[DIFF-BACKFILL] 回填失败: {e}')


def create_performance_indexes():
    """创建性能优化索引"""
    try:
        print("开始创建性能优化索引...")
        
        # 定义需要创建的索引（MySQL不支持IF NOT EXISTS，使用try-catch处理）
        indexes = [
            # 用户表索引
            ("idx_user_email", "CREATE INDEX idx_user_email ON user(email)"),
            ("idx_user_created_at", "CREATE INDEX idx_user_created_at ON user(created_at)"),
            
            # 项目表索引
            ("idx_project_user_id", "CREATE INDEX idx_project_user_id ON project(user_id)"),
            ("idx_project_status", "CREATE INDEX idx_project_status ON project(status)"),
            ("idx_project_created_at", "CREATE INDEX idx_project_created_at ON project(created_at)"),
            ("idx_project_name", "CREATE INDEX idx_project_name ON project(name)"),
            
            # 项目权限表索引
            ("idx_permission_user_id", "CREATE INDEX idx_permission_user_id ON project_permission(user_id)"),
            ("idx_permission_project_id", "CREATE INDEX idx_permission_project_id ON project_permission(project_id)"),
            ("unique_user_project", "CREATE UNIQUE INDEX unique_user_project ON project_permission(user_id, project_id)"),
            
            # BadCase表索引
            ("idx_badcase_project_id", "CREATE INDEX idx_badcase_project_id ON bad_case(project_id)"),
            ("idx_badcase_creator_id", "CREATE INDEX idx_badcase_creator_id ON bad_case(creator_id)"),
            ("idx_badcase_status", "CREATE INDEX idx_badcase_status ON bad_case(status)"),
            ("idx_badcase_priority", "CREATE INDEX idx_badcase_priority ON bad_case(priority)"),
            ("idx_badcase_created_at", "CREATE INDEX idx_badcase_created_at ON bad_case(created_at)"),
            # 复合索引 - 优化项目BadCase查询
            ("idx_badcase_project_status", "CREATE INDEX idx_badcase_project_status ON bad_case(project_id, status)"),
            ("idx_badcase_project_created", "CREATE INDEX idx_badcase_project_created ON bad_case(project_id, created_at)"),
            
            # 评论表索引
            ("idx_comment_badcase_id", "CREATE INDEX idx_comment_badcase_id ON comment(badcase_id)"),
            ("idx_comment_user_id", "CREATE INDEX idx_comment_user_id ON comment(user_id)"),
            ("idx_comment_created_at", "CREATE INDEX idx_comment_created_at ON comment(created_at)"),
            
            # 提示模板表索引
            ("idx_template_project_id", "CREATE INDEX idx_template_project_id ON prompt_template(project_id)"),
            ("idx_template_name", "CREATE INDEX idx_template_name ON prompt_template(name)"),
            
            # 计划表索引
            ("idx_plan_project_id", "CREATE INDEX idx_plan_project_id ON plan(project_id)"),
            ("idx_plan_parent_id", "CREATE INDEX idx_plan_parent_id ON plan(parent_id)"),
            # 计划类型字段已移除
            ("idx_plan_status", "CREATE INDEX idx_plan_status ON plan(status)"),
            ("idx_plan_creator_id", "CREATE INDEX idx_plan_creator_id ON plan(creator_id)"),
            ("idx_plan_assignee_id", "CREATE INDEX idx_plan_assignee_id ON plan(assignee_id)"),
            
            # Bug表索引
            ("idx_bug_project_id", "CREATE INDEX idx_bug_project_id ON bug(project_id)"),
            ("idx_bug_plan_id", "CREATE INDEX idx_bug_plan_id ON bug(plan_id)"),
            ("idx_bug_creator_id", "CREATE INDEX idx_bug_creator_id ON bug(creator_id)"),
            ("idx_bug_assignee_id", "CREATE INDEX idx_bug_assignee_id ON bug(assignee_id)"),
            ("idx_bug_status", "CREATE INDEX idx_bug_status ON bug(status)"),
            ("idx_bug_priority", "CREATE INDEX idx_bug_priority ON bug(priority)"),
            ("idx_bug_severity", "CREATE INDEX idx_bug_severity ON bug(severity)"),
            
            # Bug评论表索引
            ("idx_bug_comment_bug_id", "CREATE INDEX idx_bug_comment_bug_id ON bug_comment(bug_id)"),
            ("idx_bug_comment_user_id", "CREATE INDEX idx_bug_comment_user_id ON bug_comment(user_id)"),
            ("idx_test_case_comment_tc_id", "CREATE INDEX idx_test_case_comment_tc_id ON test_case_comment(test_case_id)"),
            ("idx_test_case_comment_user_id", "CREATE INDEX idx_test_case_comment_user_id ON test_case_comment(user_id)"),
            ("idx_test_case_comment_msg_id", "CREATE INDEX idx_test_case_comment_msg_id ON test_case_comment(source_message_id)"),
            
            # BadCase表新增索引
            ("idx_badcase_plan_id", "CREATE INDEX idx_badcase_plan_id ON bad_case(plan_id)"),

            # DiffReview 持久化索引
            ("idx_diff_review_project_target", "CREATE INDEX idx_diff_review_project_target ON diff_review_state(project_id, target, target_id)"),
            ("idx_diff_review_project_status", "CREATE INDEX idx_diff_review_project_status ON diff_review_state(project_id, status)"),
            ("idx_diff_review_plan", "CREATE INDEX idx_diff_review_plan ON diff_review_state(project_id, plan_id)"),
            ("unique_diff_review_record", "CREATE UNIQUE INDEX unique_diff_review_record ON diff_review_state(project_id, target, target_id)"),

            # 聊天历史：按会话分页取最新（GET /api/chat-sessions/:id?limit&before_id）
            # 关键查询形态：WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?
            ("idx_chat_message_session_id_id", "CREATE INDEX idx_chat_message_session_id_id ON chat_message(session_id, id)"),
            # 兼容旧路径（按时间排序/统计）
            ("idx_chat_message_session_created", "CREATE INDEX idx_chat_message_session_created ON chat_message(session_id, created_at)"),

            ("idx_wf_inapp_user_created", "CREATE INDEX idx_wf_inapp_user_created ON workflow_in_app_notification(user_id, created_at)"),
            ("idx_wf_inapp_project", "CREATE INDEX idx_wf_inapp_project ON workflow_in_app_notification(project_id)"),
            ("idx_wf_inapp_unread", "CREATE INDEX idx_wf_inapp_unread ON workflow_in_app_notification(user_id, read_at)"),
        ]
        
        # 执行索引创建
        for index_name, index_sql in indexes:
            try:
                db.session.execute(text(index_sql))
                print(f"已创建索引: {index_name}")
            except Exception as e:
                # 如果索引已存在，忽略错误
                if "Duplicate key name" not in str(e) and "already exists" not in str(e):
                    print(f"创建索引失败 {index_name}: {e}")
                else:
                    print(f"索引 {index_name} 已存在，跳过")
        
        db.session.commit()
        print("性能优化索引创建完成")
        
    except Exception as e:
        print(f"创建索引时发生错误: {e}")
        db.session.rollback()

