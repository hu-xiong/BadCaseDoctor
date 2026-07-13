from unittest.mock import MagicMock

from memory.es_work_item_store import ESWorkItemStore, WorkItemSearchConfig
from memory.es_long_memory import ESConfig


def test_hybrid_search_uses_top_level_knn_not_bool_nested():
  es = MagicMock()
  es.indices.exists.return_value = True
  es.search.return_value = {"hits": {"hits": []}}
  store = ESWorkItemStore(
    ESConfig(host="localhost", port=9200),
    WorkItemSearchConfig(alias="bcd_work_item"),
  )
  store._es = es
  vec = [0.1] * 8
  store.hybrid_search(
    project_id=1,
    query_text="hx 紧急",
    query_embedding=vec,
    entity_types=["bug"],
    top_k=5,
  )
  body = es.search.call_args.kwargs.get("body") or es.search.call_args.args[1]
  assert "knn" in body
  assert body["knn"]["field"] == "embedding"
  assert body["knn"]["k"] == 5
  q = body.get("query") or {}
  bool_q = q.get("bool") or {}
  for clause in (bool_q.get("must") or []) + (bool_q.get("should") or []):
    assert "knn" not in clause
  knn_flt = (body["knn"].get("filter") or {}).get("bool", {}).get("filter") or []
  assert knn_flt == [{"term": {"project_id": 1}}]


def test_filter_only_without_text_has_no_must_clause():
  es = MagicMock()
  es.indices.exists.return_value = True
  es.search.return_value = {"hits": {"hits": []}}
  store = ESWorkItemStore(
    ESConfig(host="localhost", port=9200),
    WorkItemSearchConfig(alias="bcd_work_item"),
  )
  store._es = es
  store.hybrid_search(
    project_id=1,
    query_text=None,
    query_embedding=None,
    top_k=8,
  )
  body = es.search.call_args.kwargs.get("body") or es.search.call_args[1]
  bool_q = (body.get("query") or {}).get("bool") or {}
  assert not bool_q.get("must")
  assert bool_q.get("filter") == [{"term": {"project_id": 1}}]


def test_base_filters_project_only():
  store = ESWorkItemStore(
    ESConfig(host="localhost", port=9200),
    WorkItemSearchConfig(alias="bcd_work_item"),
  )
  assert store._base_filters(project_id=1) == [{"term": {"project_id": 1}}]
