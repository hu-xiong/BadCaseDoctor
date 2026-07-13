"""Prometheus 文本导出与 modify 观测摘要。"""

from prometheus_client import CollectorRegistry, Counter

from badcase_sdk.text_export import collect_metric_samples, write_snapshot
from utils.observability import summarize_modify_observation, truncate_modifications_for_trace


def test_write_snapshot_and_summarize_modify(tmp_path):
    reg = CollectorRegistry()
    c = Counter("test_bcd_export_x", "doc", registry=reg)
    c.inc()
    prom, summary = write_snapshot(tmp_path, prefix="test", registry=reg)
    assert prom.is_file()
    assert summary.is_file()
    samples = collect_metric_samples(reg)
    assert any(s["name"] == "test_bcd_export_x_total" for s in samples)

    obs = {
        "success": True,
        "diff": [
            {
                "field": "expected_result",
                "lines": [
                    {"type": "delete", "content": "a"},
                    {"type": "add", "content": "b"},
                ],
            },
            {
                "field": "actual_result",
                "lines": [
                    {"type": "delete", "content": "x"},
                    {"type": "add", "content": "x"},
                ],
            },
        ],
        "modifications": {"expected_result": {"new": "b"}, "actual_result": {"new": "x"}},
    }
    s = summarize_modify_observation(obs)
    assert s["verdict"] == "partial_diff"
    assert "expected_result" in s["effective_change_fields"]
    assert "actual_result" not in s["effective_change_fields"]

    mods = truncate_modifications_for_trace({"expected_result": {"old": "1", "new": "2"}})
    assert mods["expected_result"]["new"] == "2"
