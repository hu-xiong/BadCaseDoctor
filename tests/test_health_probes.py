# -*- coding: utf-8 -*-
from app_services.health_probes import liveness_payload, readiness_payload


def test_liveness_ok():
    body = liveness_payload()
    assert body["status"] == "ok"
    assert body["service"] == "badcase-doctor"


def test_readiness_ok():
    body, code = readiness_payload(True, True)
    assert code == 200
    assert body["db_ok"] is True
    assert body["redis_ok"] is True


def test_readiness_db_fail():
    body, code = readiness_payload(False, None)
    assert code == 503
    assert body["status"] == "unavailable"
    assert body["db_ok"] is False
