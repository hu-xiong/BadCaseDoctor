from agents.tools import grep_hybrid_search as ghs


def test_lists_from_es_hits_without_orm():
    hits = [
        {
            "entity_type": "bug",
            "record_id": "714023773770092544",
            "title": "登录的bug，邮箱不能收到验证码",
            "status": "new",
            "priority": "p3",
            "assignee_id": 2,
            "plan_id": 1,
            "score": 12.5,
        }
    ]
    bugs, bcs = ghs._lists_from_es_hits(hits, entity_types=["bug"], keywords="验证码")
    assert len(bugs) == 1
    assert bugs[0]["id"] == 714023773770092544
    assert bugs[0]["title"] == "登录的bug，邮箱不能收到验证码"
    assert bugs[0]["_search_backend"] == "es_hybrid"
    assert bcs == []
