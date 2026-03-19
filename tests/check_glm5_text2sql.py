import os
import time
import json
import sys


def main():
    # 确保可从项目根目录导入
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 独立调试 GLM-5 Text2SQL：验证是否能正常生成 SQL、耗时多少、是否报错
    from agents.tools.sqlcoder_agent import Text2SQLAgent, LLMBackend, ExecutionMode

    db_path = os.getenv("TEXT2SQL_DB_PATH", "instance/badcase_doctor.db")
    execution_mode = os.getenv("TEXT2SQL_EXECUTION_MODE", "direct").lower()
    exec_mode = ExecutionMode.SANDBOX if execution_mode == "sandbox" else ExecutionMode.DIRECT

    agent = Text2SQLAgent(
        database_path=db_path,
        llm_backend=LLMBackend.GLM_5,
        debug=True,
        execution_mode=exec_mode,
    )

    question = os.getenv("TEXT2SQL_QUESTION", "查询 test_case 表中最新 5 条记录的 id 和 title")
    context = os.getenv("TEXT2SQL_CONTEXT", "只返回必要字段，按 id 倒序。")

    print("\n=== GLM-5 Text2SQL: generate_sql ===")
    print("db_path:", db_path)
    print("execution_mode:", exec_mode.value)
    print("question:", question)
    print("context:", context)

    t0 = time.time()
    try:
        result = agent.generate_sql(question, context)
    except Exception as e:
        dt = time.time() - t0
        print(f"\ngenerate_sql 异常: {e}\n耗时: {dt:.2f}s")
        raise

    dt = time.time() - t0
    print(f"\n耗时: {dt:.2f}s")
    print("raw result:", json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("success"):
        raise SystemExit("\ngenerate_sql 返回 success=False，请检查 API_KEY / 网络 / 模型权限。\n")

    sql = result.get("sql") or ""
    print("\n=== SQL ===")
    print(sql)

    # 可选：执行 SQL（默认不执行，避免对环境造成影响；若是 SELECT 可安全执行）
    if os.getenv("TEXT2SQL_RUN_SQL", "0") == "1":
        print("\n=== execute_sql ===")
        t1 = time.time()
        exec_result = agent.execute_sql(sql)
        dt2 = time.time() - t1
        print(f"耗时: {dt2:.2f}s")
        print(json.dumps(exec_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

