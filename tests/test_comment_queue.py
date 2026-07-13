import json
from unittest.mock import MagicMock

from utils import comment_queue as cq


def test_new_client_temp_id_unique():
    a = cq.new_client_temp_id()
    b = cq.new_client_temp_id()
    assert a.startswith("pending-")
    assert a != b


def test_enqueue_and_store_result():
    redis = MagicMock()
    job = {"entity_type": "bug", "entity_id": 1, "content": "hi"}
    assert cq.enqueue(redis, job) is True
    redis.lpush.assert_called_once()
    key, payload = redis.lpush.call_args[0]
    assert key == cq.COMMENT_QUEUE_KEY
    assert json.loads(payload)["content"] == "hi"

    cq.store_result(redis, "pending-abc", {"id": 9})
    redis.setex.assert_called_once()
    set_key, ttl, raw = redis.setex.call_args[0]
    assert set_key == f"{cq.COMMENT_RESULT_PREFIX}pending-abc"
    assert ttl == cq.RESULT_TTL_SEC
    assert json.loads(raw)["id"] == 9


def test_enqueue_without_redis_returns_false():
    assert cq.enqueue(None, {"x": 1}) is False
