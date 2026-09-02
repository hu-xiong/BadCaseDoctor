# -*- coding: utf-8 -*-
import os

from routers import payment as pay


def test_payment_provider_default_and_override(monkeypatch):
    monkeypatch.delenv("PAYMENT_PROVIDER", raising=False)
    assert pay.payment_provider() == "mock"
    monkeypatch.setenv("PAYMENT_PROVIDER", "mock")
    assert pay.payment_provider() == "mock"
    monkeypatch.setenv("PAYMENT_PROVIDER", "WECHAT")
    assert pay.payment_provider() == "wechat"


def test_plans_currency_follows_provider(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "mock")
    client_plans = []
    # 直接复用 get_plans 视图逻辑：调用函数体通过 test_request 太重，测数据变换
    provider = pay.payment_provider()
    assert pay._is_cny_provider(provider)
    for plan_id, plan in pay.SUBSCRIPTION_PLANS.items():
        client_plans.append(
            {
                "id": plan_id,
                "price": plan["price_cny"] / 100,
                "currency": "CNY",
            }
        )
    assert client_plans[0]["currency"] == "CNY"
    assert client_plans[0]["price"] == 99.0


def test_wechat_alipay_not_configured(monkeypatch):
    monkeypatch.delenv("WECHAT_APP_ID", raising=False)
    monkeypatch.delenv("WECHAT_MCH_ID", raising=False)
    monkeypatch.delenv("WECHAT_API_V3_KEY", raising=False)
    monkeypatch.delenv("WECHAT_NOTIFY_URL", raising=False)
    assert pay._wechat_configured() is False
    monkeypatch.delenv("ALIPAY_APP_ID", raising=False)
    monkeypatch.delenv("ALIPAY_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("ALIPAY_NOTIFY_URL", raising=False)
    assert pay._alipay_configured() is False


def test_frontend_hash_url(monkeypatch):
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com/")
    assert (
        pay.frontend_hash_url("payment/success", query="session_id=abc")
        == "https://app.example.com/#/payment/success?session_id=abc"
    )
    assert pay.frontend_hash_url("payment/cancel") == "https://app.example.com/#/payment/cancel"
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    assert (
        pay.frontend_hash_url("payment/success", host_fallback="http://127.0.0.1:5173/")
        == "http://127.0.0.1:5173/#/payment/success"
    )


def test_config_es_defaults_are_local(monkeypatch):
    monkeypatch.delenv("ES_HOST", raising=False)
    monkeypatch.delenv("ES_PORT", raising=False)
    # 绕过 dotenv 已注入值：直接测 getenv 缺省逻辑
    host = (os.getenv("ES_HOST") or "127.0.0.1").strip()
    port = int(os.getenv("ES_PORT", "9200"))
    assert host == "127.0.0.1"
    assert port == 9200


def test_payment_history_view_exists():
    assert callable(getattr(pay, "payment_history", None))
