from agents.locale_prompts import try_rule_based_incremental_running_summary


def test_rule_fast_grep_short_obs():
    md = try_rule_based_incremental_running_summary(
        "zh",
        "",
        0,
        "grep",
        "登录 bug",
        "grep 命中 4 条 Bug，已写入导航。",
    )
    assert md is not None
    assert "## 已确认" in md
    assert "grep" in md


def test_rule_fast_skips_long_prev():
    md = try_rule_based_incremental_running_summary(
        "zh",
        "## 已确认\n" + "- x\n" * 200,
        1,
        "grep",
        "t",
        "短观察",
    )
    assert md is None
