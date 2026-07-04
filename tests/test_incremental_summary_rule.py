from agents.locale_prompts import (
    enrich_nl_observation_for_incremental_summary_llm,
    incremental_running_summary_prompt,
    modify_summary_preview,
    react_summarize_cdp_done,
)


def test_enrich_cdp_observation_for_llm_includes_elements():
    blob = enrich_nl_observation_for_incremental_summary_llm(
        "cdp",
        "页面快照 14 个可交互元素 · 登录页（http://localhost:5173/#/login）",
        {
            "success": True,
            "tool": "cdp_snapshot",
            "url": "http://localhost:5173/#/login",
            "title": "Vite + Vue",
            "stats": {"exported": 14},
            "nodes": [
                {"ref": "@e1", "role": "textbox", "name": "用户名"},
                {"ref": "@e2", "role": "textbox", "name": "密码"},
            ],
        },
        "zh",
    )
    assert "[snapshot.interactive_count] 14" in blob
    assert "用户名" in blob
    assert "[page.route] 登录页" in blob
    assert "勿只写「cdp 成功」" in blob


def test_enrich_non_cdp_passthrough():
    assert (
        enrich_nl_observation_for_incremental_summary_llm(
            "grep", "命中 3 条 Bug", None, "zh"
        )
        == "命中 3 条 Bug"
    )


def test_incremental_summary_prompt_requires_natural_confirmed():
    p = incremental_running_summary_prompt(
        "zh", "", 0, "grep", "定位 bug", "命中 2 条"
    )
    assert "## 已确认" in p
    assert "自然语言" in p or "可核对" in p

    p_cdp = incremental_running_summary_prompt(
        "zh", "", 0, "cdp", "测登录", "观察摘要"
    )
    assert "cdp" in p_cdp.lower() or "浏览器" in p_cdp
    assert "禁止" in p_cdp or "勿" in p_cdp


def test_react_summarize_cdp_session_create():
    nl = react_summarize_cdp_done(
        {
            "success": True,
            "action": "create",
            "session_id": "sess_abc1234567",
            "page": {
                "url": "http://localhost:5173/#/project-detail/2",
                "title": "Vite + Vue",
            },
        },
        "zh",
    )
    assert "project-detail" in nl
    assert "项目详情页" in nl
    assert "Vite + Vue" not in nl


def test_react_summarize_cdp_snapshot_with_nodes():
    nl = react_summarize_cdp_done(
        {
            "success": True,
            "tool": "cdp_snapshot",
            "snapshot_id": "snap_1",
            "url": "http://localhost:5173/#/login",
            "title": "Vite + Vue",
            "stats": {"exported": 3},
            "nodes": [
                {"ref": "@e1", "role": "button", "name": "Vite + Vue"},
                {"ref": "@e2", "role": "textbox", "name": "用户名"},
                {"ref": "@e3", "role": "textbox", "name": "密码"},
            ],
        },
        "zh",
    )
    assert "3" in nl
    assert "登录页" in nl
    assert "用户名" in nl
    assert "Vite + Vue" not in nl


def test_react_summarize_cdp_explore_inventory():
    nl = react_summarize_cdp_done(
        {
            "success": True,
            "action": "explore",
            "phase": "inventory",
            "url": "http://localhost:5173/#/project-detail/3",
            "title": "Vite + Vue",
            "element_count": 3,
            "element_inventory": [
                {"ref": "@e1", "role": "button", "name": "新建迭代"},
                {"ref": "@e2", "role": "button", "name": "+ 新增卡片"},
                {"ref": "@e3", "role": "combobox", "name": "全部类型"},
            ],
        },
        "zh",
    )
    assert "界面元素清单" in nl
    assert "项目详情页" in nl
    assert "新建迭代" in nl
    assert "新增卡片" in nl
    assert "全部类型" in nl


def test_react_summarize_cdp_explore_full_with_issues():
    nl = react_summarize_cdp_done(
        {
            "success": False,
            "action": "explore",
            "phase": "full",
            "url": "http://localhost:5173/#/project-detail/3",
            "element_count": 2,
            "element_inventory": [
                {"ref": "@e1", "role": "button", "name": "+ 新增卡片"},
                {"ref": "@e2", "role": "combobox", "name": "全部类型"},
            ],
            "exploration_clicks": 5,
            "issues_found": 1,
            "exploration_issues": [
                {"message": "点击 @e2 (combobox/全部类型) 失败：box model"},
            ],
        },
        "zh",
    )
    assert "CDP 探测完成" in nl
    assert "新增卡片" in nl
    assert "点击 5 次" in nl
    assert "box model" in nl


def test_enrich_cdp_explore_observation_for_llm_includes_inventory():
    blob = enrich_nl_observation_for_incremental_summary_llm(
        "cdp",
        "界面元素清单：共 2 个可交互控件 · 项目详情页 · 控件：@e1 (button/新建迭代)",
        {
            "success": True,
            "action": "explore",
            "phase": "inventory",
            "url": "http://localhost:5173/#/project-detail/3",
            "element_count": 2,
            "element_inventory": [
                {"ref": "@e1", "role": "button", "name": "新建迭代"},
                {"ref": "@e2", "role": "button", "name": "+ 新增卡片"},
            ],
        },
        "zh",
    )
    assert "[explore.element_count] 2" in blob
    assert "[explore.inventory]" in blob
    assert "新建迭代" in blob
    assert "禁止引用 grep" in blob
    assert "[page.route] 项目详情页" in blob


def test_modify_summary_preview_includes_title():
    s = modify_summary_preview(
        "badcase",
        710034681191411712,
        "优先级:p3",
        "zh",
        record_title="对话有问题，问进京证不能很好答完整",
    )
    assert "对话有问题" in s
    assert "710034681191411712" in s
