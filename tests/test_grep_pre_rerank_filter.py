from agents.tools import grep_hybrid_search as ghs


def test_pre_rerank_min_score_vector_only_default():
    cfg = type("C", (), {"GREP_PRE_RERANK_MIN_SCORE": 0.90})()
    assert ghs._pre_rerank_min_score(cfg, need_vector=True, search_mode="vector_only") == 0.90
    assert ghs._pre_rerank_min_score(cfg, need_vector=True, search_mode="hybrid") == 0.90
    assert ghs._pre_rerank_min_score(cfg, need_vector=False, search_mode="bm25_only") == 0.0
    assert ghs._pre_rerank_min_score(cfg, need_vector=True, search_mode="bm25_only") == 0.0


def test_filter_es_hits_pre_rerank():
    hits = [
        {"score": 0.93, "record_id": 1},
        {"score": 0.91, "record_id": 2},
        {"score": 0.89, "record_id": 3},
    ]
    kept, dropped = ghs._filter_es_hits_pre_rerank(hits, 0.90)
    assert dropped == 1
    assert len(kept) == 2
    assert kept[0]["record_id"] == 1
    assert kept[1]["record_id"] == 2
