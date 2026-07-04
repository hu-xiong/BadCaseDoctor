from unittest.mock import patch

from agents.tools import grep_es_rerank as rerank_mod
from memory.qwen_rerank_client import RerankHit


def test_grep_user_query_text_prefers_raw_without_ui_block():
    q = rerank_mod.grep_user_query_text(
        raw_user_input="把状态改成重新打开",
        user_input="[界面上下文]\n- record_id=123\n把状态改成重新打开",
    )
    assert q == "把状态改成重新打开"
    assert "[界面上下文]" not in q


def test_semantic_text_for_grep_embed_strips_ui_block():
    raw = (
        "[界面上下文] 用户当前在应用中聚焦的记录\n"
        "- target=bug\n- record_id=714021551925628928\n"
        "当前沙箱一次性把之前的diff展示出来了bug的状态修改成重新打开"
    )
    q = rerank_mod.semantic_text_for_grep_embed(raw)
    assert "[界面上下文]" not in q
    assert "record_id=" not in q
    assert "重新打开" in q


def test_compose_rerank_query_keywords_only():
    q = rerank_mod._compose_rerank_query(
        user_input="[界面上下文] 用户当前在应用中聚焦的记录\n- target=bug\n登录的bug邮箱验证码",
        keywords="登录的bug，邮箱不能收到验证码",
        assignee="hx",
        status="new",
    )
    assert q == "登录的bug，邮箱不能收到验证码"
    assert "[界面上下文]" not in q
    assert "target=" not in q


def test_bug_rerank_document_includes_fields():
    doc = rerank_mod._bug_rerank_document(
        {
            "title": "登录失败",
            "status": "new",
            "priority": "p3",
            "assignee_id": 2,
            "fields": {
                "severity": "major",
                "steps_to_reproduce": "点击登录",
                "expected_result": "收到邮件",
            },
        }
    )
    assert "类型=Bug" in doc
    assert "标题=登录失败" in doc
    assert "复现步骤=点击登录" in doc
    assert "期望结果=收到邮件" in doc


@patch.object(rerank_mod, "_should_skip_rerank_api", return_value=(False, ""))
@patch.object(rerank_mod, "rerank_documents")
def test_rerank_threshold_filters(mock_rerank, _mock_skip):
    mock_rerank.return_value = (
        [
            RerankHit(index=0, score=0.9),
            RerankHit(index=1, score=0.2),
        ],
        {"status": "ok"},
    )
    bugs = [
        {"id": 1, "title": "a", "status": "new", "assignee_id": 2},
        {"id": 3, "title": "c", "status": "new", "assignee_id": 2},
    ]
    bcs = [{"id": 2, "title": "b", "status": "new", "assignee": "hx"}]
    with patch.object(rerank_mod, "_grep_rerank_enabled", return_value=True):
        ob, obc, meta = rerank_mod.rerank_es_candidates_sync(
            bug_list=bugs,
            badcase_list=bcs,
            user_input="查hx的bug",
            assignee="hx",
        )
    assert len(ob) == 1
    assert ob[0]["id"] == 1
    assert ob[0]["_rerank_score"] == 0.9
    assert len(obc) == 0
    assert meta.get("rerank") == "ok"


def test_filter_top_n_after_min_score():
    bugs = [
        {"id": 1, "title": "a", "status": "new", "assignee_id": 2},
        {"id": 2, "title": "b", "status": "new", "assignee_id": 2},
        {"id": 3, "title": "c", "status": "new", "assignee_id": 2},
        {"id": 4, "title": "d", "status": "new", "assignee_id": 2},
    ]
    entries = [("bug", row, i) for i, row in enumerate(bugs)]
    hits = [
        RerankHit(index=0, score=0.95),
        RerankHit(index=1, score=0.80),
        RerankHit(index=2, score=0.90),
        RerankHit(index=3, score=0.74),
    ]
    ob, obc, audit = rerank_mod._filter_lists_by_hits(
        bugs, [], entries, hits, min_score=0.75, top_n=2
    )
    assert len(ob) == 2
    assert ob[0]["id"] == 1
    assert ob[1]["id"] == 3
    assert ob[0]["_rerank_score"] == 0.95
    assert ob[1]["_rerank_score"] == 0.9
    assert len(audit) == 2


def test_skip_rerank_small_set():
    bugs = [
        {"id": 1, "title": "登录的bug，邮箱不能收到验证码", "keyword_match": True, "_es_score": 10},
        {"id": 2, "title": "其他", "_es_score": 5},
    ]
    with patch.object(rerank_mod, "_grep_rerank_enabled", return_value=True):
        with patch.object(rerank_mod, "rerank_documents") as mock_rr:
            ob, obc, meta = rerank_mod.rerank_es_candidates_sync(
                bug_list=bugs,
                badcase_list=[],
                keywords="登录 邮箱 验证码",
            )
    mock_rr.assert_not_called()
    assert meta.get("rerank") == "skipped_small_set"
    assert ob[0]["id"] == 1


def test_skip_rerank_es_confident_top_title():
    bugs = [
        {"id": 9, "title": "无关"},
        {"id": 1, "title": "登录的bug，邮箱不能收到验证码", "keyword_match": True},
    ]
    with patch.object(rerank_mod, "_grep_rerank_enabled", return_value=True):
        with patch.object(
            rerank_mod,
            "_should_skip_rerank_api",
            return_value=(True, "skipped_es_confident"),
        ):
            with patch.object(rerank_mod, "rerank_documents") as mock_rr:
                ob, _, meta = rerank_mod.rerank_es_candidates_sync(
                    bug_list=bugs,
                    badcase_list=[],
                    keywords="登录 邮箱 验证码",
                )
    mock_rr.assert_not_called()
    assert meta.get("rerank") == "skipped_es_confident"


def test_rerank_disabled_passthrough():
    bugs = [{"id": 1, "title": "a"}]
    with patch.object(rerank_mod, "_grep_rerank_enabled", return_value=False):
        ob, obc, meta = rerank_mod.rerank_es_candidates_sync(bug_list=bugs, badcase_list=[])
    assert ob == bugs
    assert meta.get("rerank") == "disabled"
