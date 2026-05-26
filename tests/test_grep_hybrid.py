from unittest.mock import MagicMock, patch

from agents.tools.grep_assignee import AssigneeResolveResult
from agents.tools import grep_hybrid_search as ghs


def test_hybrid_disabled_returns_none():
    with patch.object(ghs, "_grep_vector_enabled", return_value=False):
        bug, bc, meta = ghs.hybrid_search_work_items(
            project_id="1",
            keywords="login",
            assignee=None,
            status=None,
            plan_id=None,
            raw_target="bug",
        )
    assert bug is None
    assert bc is None
    assert meta.get("search_backend") == "es_hybrid"


@patch.object(ghs, "_grep_vector_enabled", return_value=True)
@patch.object(ghs, "resolve_assignee_user_ids")
@patch.object(ghs, "build_work_item_store_from_config")
def test_hybrid_no_index_falls_back_sql(mock_store, mock_resolve, _enabled):
    mock_resolve.return_value = AssigneeResolveResult(hint="hx", user_ids=[1])
    es = MagicMock()
    es.indices.exists.return_value = False
    mock_store.return_value = MagicMock(
        es=es, search_cfg=MagicMock(alias="bcd_work_item"), alias_exists=MagicMock(return_value=False)
    )
    with patch.object(ghs, "_grep_skip_alias_exists", return_value=False):
        bug, bc, _meta = ghs.hybrid_search_work_items(
            project_id="1",
            keywords="x",
            assignee="hx",
            status=None,
            plan_id=None,
            raw_target="all",
        )
    assert bug is None
    assert bc is None


@patch.object(ghs, "_grep_vector_enabled", return_value=True)
@patch.object(ghs, "resolve_assignee_user_ids")
@patch.object(ghs, "build_work_item_store_from_config")
def test_hybrid_card_target_uses_bug_badcase_entity_types(mock_store, mock_resolve, _enabled):
    mock_resolve.return_value = AssigneeResolveResult(hint="hx", user_ids=[2])
    es = MagicMock()
    es.indices.exists.return_value = False
    mock_store.return_value = MagicMock(
        es=es, search_cfg=MagicMock(alias="bcd_work_item"), alias_exists=MagicMock(return_value=False)
    )
    with patch.object(ghs, "_grep_skip_alias_exists", return_value=False):
        bug, bc, _meta = ghs.hybrid_search_work_items(
            project_id="1",
            keywords=None,
            assignee="hx",
            status=None,
            plan_id=None,
            raw_target="card",
        )
    assert bug is None
    assert bc is None


@patch.object(ghs, "_grep_vector_enabled", return_value=True)
@patch.object(ghs, "resolve_assignee_user_ids")
@patch.object(ghs, "build_work_item_store_from_config")
@patch.object(ghs, "build_embedding_client_from_config")
def test_hybrid_es_ran_empty_skips_sql(mock_embed, mock_store, mock_resolve, _enabled):
    mock_resolve.return_value = AssigneeResolveResult(hint="hx", user_ids=[2])
    mock_embed.return_value = MagicMock(embed=MagicMock(return_value=[0.1, 0.2]))
    es = MagicMock()
    es.indices.exists.return_value = True
    es.search = MagicMock(return_value={"hits": {"hits": []}})
    store = MagicMock(
        es=es, search_cfg=MagicMock(alias="bcd_work_item"), alias_exists=MagicMock(return_value=True)
    )
    store.hybrid_search.return_value = []
    mock_store.return_value = store
    bug, bc, meta = ghs.hybrid_search_work_items(
            project_id="1",
            keywords=None,
            assignee="hx",
            status=None,
            plan_id=None,
        raw_target="bug",
    )
    assert bug == []
    assert bc is None
    assert meta.get("es_ran") is True
    assert meta.get("hydrate") == "es_source"


@patch.object(ghs, "_grep_vector_enabled", return_value=True)
def test_hybrid_skips_testcase_target(_enabled):
    bug, bc, _meta = ghs.hybrid_search_work_items(
        project_id="1",
        keywords="x",
        assignee=None,
        status=None,
        plan_id=None,
        raw_target="testcase",
    )
    assert bug is None
    assert bc is None
