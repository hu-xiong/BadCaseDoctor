"""ES 命中时跳过 Card 全表 SQL。"""
from agents.tools.grep_tool import GrepTool


def test_skip_card_sql_when_target_bug_and_es_hits():
    tool = GrepTool()
    assert tool._grep_should_skip_card_full_scan(
        raw_target="bug",
        hybrid_bug=True,
        hybrid_bc=False,
        bug_list=[{"id": 1}],
        badcase_list=[],
    )


def test_skip_card_sql_when_target_bug_sql_fallback_hits():
    """ES 失败走 SQL 仍有 bug 列表时也应跳过 Card 全表。"""
    tool = GrepTool()
    assert tool._grep_should_skip_card_full_scan(
        raw_target="bug",
        hybrid_bug=False,
        hybrid_bc=False,
        bug_list=[{"id": 1}],
        badcase_list=[],
    )


def test_no_skip_card_sql_when_target_bug_without_hits():
    tool = GrepTool()
    assert not tool._grep_should_skip_card_full_scan(
        raw_target="bug",
        hybrid_bug=False,
        hybrid_bc=False,
        bug_list=[],
        badcase_list=[],
    )


def test_skip_card_sql_when_target_card_and_es_hits():
    tool = GrepTool()
    assert tool._grep_should_skip_card_full_scan(
        raw_target="card",
        hybrid_bug=True,
        hybrid_bc=False,
        bug_list=[{"id": 1}],
        badcase_list=[],
    )
