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
