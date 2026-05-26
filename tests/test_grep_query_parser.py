from agents.tools.grep_query_parser import (
    enrich_grep_params,
    extract_assignee_from_natural_language,
    parse_structured_grep_keywords,
)


def test_parse_assignee_from_keywords():
    kw, asn, st = parse_structured_grep_keywords("负责人:hx 登录", assignee=None)
    assert asn == "hx"
    assert kw == "登录"
    assert st is None


def test_extract_assignee_from_nl_hx_bug():
    text = "将负责人 hx的bug都检索出来"
    assert extract_assignee_from_natural_language(text) == "hx"


def test_enrich_strips_keywords_and_sets_assignee():
    parsed = enrich_grep_params(
        keywords="负责人:hx",
        assignee=None,
        user_input="将负责人 hx的bug都检索出来",
        target="bug",
    )
    assert parsed.assignee == "hx"
    assert parsed.keywords is None
    assert parsed.entity_types == ["bug"]
