from unittest.mock import patch

from agents.tools import grep_es_llm_judge as judge


def test_parse_match_ids_json():
    raw = '{"match_ids":["bug:1","badcase:2"]}'
    assert judge._parse_match_ids(raw) == {"bug:1", "badcase:2"}


def test_parse_match_ids_empty():
    assert judge._parse_match_ids('{"match_ids":[]}') == set()


def test_llm_judge_enabled_respects_config_false_boolean():
    class _Cfg:
        GREP_ES_LLM_JUDGE = False
        GREP_VECTOR_ENABLED = True

    assert judge._grep_es_llm_judge_enabled(_Cfg) is False


def test_skip_llm_judge_when_rerank_api_skipped():
    class _Cfg:
        GREP_SKIP_LLM_JUDGE_IF_RERANKED = True
        GREP_SKIP_LLM_JUDGE_IF_NO_RERANK_API = True

    skip, reason = judge._should_skip_llm_judge({"rerank": "skipped_small_set"}, _Cfg)
    assert skip is True
    assert reason == "skipped_no_rerank_api"


def test_judge_disabled_passthrough():
    bugs = [{"id": 1, "title": "a"}]
    with patch.object(judge, "_grep_es_llm_judge_enabled", return_value=False):
        ob, obc, meta = judge.llm_judge_es_candidates_sync(bug_list=bugs, badcase_list=[])
    assert ob == bugs
    assert meta.get("llm_judge") == "disabled"


def test_compose_user_intent():
    s = judge._compose_user_intent(
        user_input="查负责人hx的bug",
        keywords=None,
        assignee="hx",
        status=None,
    )
    assert "hx" in s
    assert "查负责人hx的bug" in s
