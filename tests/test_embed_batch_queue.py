import time
from unittest.mock import MagicMock

from memory.embed_batch_queue import EmbedBatchQueue, _PendingEmbed


def _item(n: int) -> _PendingEmbed:
    return _PendingEmbed(
        doc_id=f"bug:{n}",
        search_text=f"text-{n}",
        doc_body={"title": f"t{n}"},
        content_hash=f"h{n}",
    )


def test_flush_on_batch_size():
    embed_fn = MagicMock(return_value=[[0.1], [0.2]])
    upsert_fn = MagicMock(return_value=2)
    q = EmbedBatchQueue(batch_size=2, flush_ms=300, embed_fn=embed_fn, upsert_fn=upsert_fn)
    q.enqueue(_item(1))
    assert embed_fn.call_count == 0
    q.enqueue(_item(2))
    assert embed_fn.call_count == 1
    assert len(embed_fn.call_args[0][0]) == 2


def test_flush_on_timeout():
    embed_fn = MagicMock(return_value=[[0.1]])
    upsert_fn = MagicMock(return_value=1)
    q = EmbedBatchQueue(batch_size=16, flush_ms=80, embed_fn=embed_fn, upsert_fn=upsert_fn)
    q.enqueue(_item(1))
    assert embed_fn.call_count == 0
    time.sleep(0.12)
    assert embed_fn.call_count == 1
