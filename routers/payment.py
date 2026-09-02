# routers/payment.py
"""
订阅支付：Stripe（国际）+ 微信/支付宝骨架 + mock（私有化联调）。
PAYMENT_PROVIDER=stripe|wechat|alipay|mock
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

payment_bp = Blueprint("payment", __name__)

try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None

# Stripe 配置（未安装 stripe 包时跳过）
if stripe is not None:
    stripe.api_key = (os.getenv("STRIPE_SECRET_KEY") or "").strip() or None
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()

# 订阅计划：price=美分；price_cny=分（人民币）
SUBSCRIPTION_PLANS = {
    "basic": {
        "name": "Basic",
        "name_zh": "基础版",
        "price": 2000,
        "price_cny": 9900,
        "credits": 100,
        "description": "100 credits",
        "description_zh": "100 次 Agent 额度",
    },
    "standard": {
        "name": "Standard",
        "name_zh": "标准版",
        "price": 4000,
        "price_cny": 19900,
        "credits": 250,
        "description": "250 credits",
        "description_zh": "250 次 Agent 额度",
    },
    "professional": {
        "name": "Professional",
        "name_zh": "专业版",
        "price": 6000,
        "price_cny": 39900,
        "credits": 500,
        "description": "500 credits",
        "description_zh": "500 次 Agent 额度",
    },
    "enterprise": {
        "name": "Enterprise",
        "name_zh": "企业版",
        "price": 10000,
        "price_cny": 79900,
        "credits": 1200,
        "description": "1200 credits",
        "description_zh": "1200 次 Agent 额度",
    },
}


def payment_provider() -> str:
    # 默认 mock：本地/私有化联调可立刻入账；上线 Stripe/微信/支付宝时显式配置
    raw = (os.getenv("PAYMENT_PROVIDER") or "mock").strip().lower()
    if raw in ("stripe", "wechat", "alipay", "mock"):
        return raw
    return "mock"


def frontend_hash_url(route: str, *, query: str = "", host_fallback: str | None = None) -> str:
    """
    前端为 hash 路由（#/payment/success）。外部支付回跳必须指向前端站，不能用 API host。
    优先 FRONTEND_BASE_URL；未配置时回退 host_fallback / request.host_url（仅适合同源或本地 mock）。
    """
    base = (os.getenv("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    if not base:
        base = (host_fallback or "").strip().rstrip("/")
    if not base:
        try:
            base = (request.host_url or "").rstrip("/")
        except Exception:
            base = ""
    path = (route or "").lstrip("/")
    url = f"{base}/#/{path}" if base else f"/#/{path}"
    if query:
        return f"{url}?{query}"
    return url


def _is_cny_provider(provider: str | None = None) -> bool:
    return (provider or payment_provider()) in ("wechat", "alipay", "mock")


def _wechat_configured() -> bool:
    return all(
        (os.getenv(k) or "").strip()
        for k in ("WECHAT_APP_ID", "WECHAT_MCH_ID", "WECHAT_API_V3_KEY", "WECHAT_NOTIFY_URL")
    )


def _alipay_configured() -> bool:
    return all(
        (os.getenv(k) or "").strip()
        for k in ("ALIPAY_APP_ID", "ALIPAY_PRIVATE_KEY", "ALIPAY_NOTIFY_URL")
    )


@payment_bp.route("/api/payment/providers", methods=["GET"])
def list_providers():
    """前端可选支付渠道与配置状态。"""
    active = payment_provider()
    return jsonify(
        {
            "active": active,
            "providers": [
                {
                    "id": "stripe",
                    "label": "Stripe (Card)",
                    "currency": "USD",
                    "configured": bool(stripe and stripe.api_key),
                    "active": active == "stripe",
                },
                {
                    "id": "wechat",
                    "label": "微信支付",
                    "currency": "CNY",
                    "configured": _wechat_configured(),
                    "active": active == "wechat",
                },
                {
                    "id": "alipay",
                    "label": "支付宝",
                    "currency": "CNY",
                    "configured": _alipay_configured(),
                    "active": active == "alipay",
                },
                {
                    "id": "mock",
                    "label": "Mock（联调）",
                    "currency": "CNY",
                    "configured": True,
                    "active": active == "mock",
                },
            ],
        }
    )


@payment_bp.route("/api/payment/plans", methods=["GET"])
def get_plans():
    """获取所有订阅计划（随 PAYMENT_PROVIDER 切换币种展示）。"""
    provider = payment_provider()
    cny = _is_cny_provider(provider)
    plans = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        if cny:
            plans.append(
                {
                    "id": plan_id,
                    "name": plan["name_zh"],
                    "price": plan["price_cny"] / 100,
                    "currency": "CNY",
                    "credits": plan["credits"],
                    "description": plan["description_zh"],
                }
            )
        else:
            plans.append(
                {
                    "id": plan_id,
                    "name": plan["name"],
                    "price": plan["price"] / 100,
                    "currency": "USD",
                    "credits": plan["credits"],
                    "description": plan["description"],
                }
            )
    return jsonify({"plans": plans, "provider": provider})


@payment_bp.route("/api/payment/create-checkout", methods=["POST"])
@login_required
def create_checkout():
    """创建支付会话 / 订单。"""
    data = request.json or {}
    plan_id = data.get("plan_id")
    if plan_id not in SUBSCRIPTION_PLANS:
        return jsonify({"error": "无效的订阅计划"}), 400

    provider = (data.get("provider") or payment_provider()).strip().lower()
    if provider == "mock":
        return _create_mock_checkout(plan_id)
    if provider == "wechat":
        return _create_wechat_checkout(plan_id)
    if provider == "alipay":
        return _create_alipay_checkout(plan_id)
    return _create_stripe_checkout(plan_id)


def _create_stripe_checkout(plan_id: str):
    if stripe is None or not stripe.api_key:
        return jsonify({"error": "Stripe 未配置（STRIPE_SECRET_KEY）"}), 503
    if not (os.getenv("FRONTEND_BASE_URL") or "").strip():
        return jsonify(
            {
                "error": "FRONTEND_BASE_URL 未配置",
                "hint": "Stripe 回跳需指向前端站，例如 https://app.example.com",
            }
        ), 503

    plan = SUBSCRIPTION_PLANS[plan_id]
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": plan["name"],
                            "description": plan["description"],
                        },
                        "unit_amount": plan["price"],
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=frontend_hash_url(
                "payment/success", query="session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=frontend_hash_url("payment/cancel"),
            metadata={
                "user_id": str(current_user.id),
                "plan_id": plan_id,
                "credits": str(plan["credits"]),
            },
            customer_email=getattr(current_user, "email", None),
        )
        return jsonify(
            {
                "provider": "stripe",
                "checkout_url": session.url,
                "session_id": session.id,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _create_mock_checkout(plan_id: str):
    """私有化 / 联调：立即入账额度，无需真实支付。"""
    allow = (os.getenv("PAYMENT_MOCK_ENABLED") or "1").strip().lower()
    if allow in ("0", "false", "no", "off"):
        return jsonify({"error": "Mock 支付已关闭（PAYMENT_MOCK_ENABLED=0）"}), 403

    plan = SUBSCRIPTION_PLANS[plan_id]
    payment_id = f"mock_{uuid.uuid4().hex}"
    _add_user_credits(
        current_user.id,
        plan["credits"],
        plan_id,
        payment_id,
        amount=plan["price_cny"],
        provider="mock",
    )
    return jsonify(
        {
            "provider": "mock",
            "status": "completed",
            "session_id": payment_id,
            "credits_added": plan["credits"],
            "redirect_url": frontend_hash_url(
                "payment/success", query=f"session_id={payment_id}"
            ),
        }
    )


def _create_wechat_checkout(plan_id: str):
    if not _wechat_configured():
        return jsonify(
            {
                "error": "微信支付未配置",
                "required_env": [
                    "WECHAT_APP_ID",
                    "WECHAT_MCH_ID",
                    "WECHAT_API_V3_KEY",
                    "WECHAT_NOTIFY_URL",
                    "WECHAT_SERIAL_NO",
                    "WECHAT_PRIVATE_KEY_PATH",
                ],
                "hint": "配置完成后将返回 Native 预下单 code_url；联调可设 PAYMENT_PROVIDER=mock",
            }
        ), 503

    plan = SUBSCRIPTION_PLANS[plan_id]
    out_trade_no = f"wx{current_user.id}_{uuid.uuid4().hex[:16]}"
    # 真实下单需 wechatpayv3 + 商户证书；此处先落 pending 订单，便于后续接 SDK
    _record_pending_payment(
        current_user.id,
        plan_id,
        plan["credits"],
        plan["price_cny"],
        out_trade_no,
        provider="wechat",
    )
    return jsonify(
        {
            "provider": "wechat",
            "status": "pending_sdk",
            "out_trade_no": out_trade_no,
            "amount_fen": plan["price_cny"],
            "description": plan["name_zh"],
            "error": "已记录待支付订单；请安装并接入 wechatpayv3 完成 Native 预下单",
        }
    ), 501


def _create_alipay_checkout(plan_id: str):
    if not _alipay_configured():
        return jsonify(
            {
                "error": "支付宝未配置",
                "required_env": [
                    "ALIPAY_APP_ID",
                    "ALIPAY_PRIVATE_KEY",
                    "ALIPAY_NOTIFY_URL",
                    "ALIPAY_PUBLIC_KEY",
                ],
                "hint": "配置完成后将返回电脑网站支付 form/url；联调可设 PAYMENT_PROVIDER=mock",
            }
        ), 503

    plan = SUBSCRIPTION_PLANS[plan_id]
    out_trade_no = f"ali{current_user.id}_{uuid.uuid4().hex[:16]}"
    _record_pending_payment(
        current_user.id,
        plan_id,
        plan["credits"],
        plan["price_cny"],
        out_trade_no,
        provider="alipay",
    )
    return jsonify(
        {
            "provider": "alipay",
            "status": "pending_sdk",
            "out_trade_no": out_trade_no,
            "amount_fen": plan["price_cny"],
            "description": plan["name_zh"],
            "error": "已记录待支付订单；请接入支付宝 SDK 完成 page.pay",
        }
    ), 501


@payment_bp.route("/api/payment/webhook", methods=["POST"])
def webhook():
    """Stripe Webhook 回调处理"""
    if stripe is None or not STRIPE_WEBHOOK_SECRET:
        return "Stripe webhook not configured", 503

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return "Invalid payload", 400
    except Exception:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session["metadata"]["user_id"])
        plan_id = session["metadata"]["plan_id"]
        credits = int(session["metadata"]["credits"])
        _add_user_credits(user_id, credits, plan_id, session["id"], provider="stripe")
        print(f"[PAYMENT] ✅ 用户 {user_id} 购买 {plan_id}，增加 {credits} 次额度")

    return "", 200


@payment_bp.route("/api/payment/notify/wechat", methods=["POST"])
def wechat_notify():
    """微信支付结果通知占位：配置商户后在此验签并入账。"""
    if not _wechat_configured():
        return jsonify({"code": "FAIL", "message": "not configured"}), 503
    # SDK 接入前拒绝假通知，避免误入账
    return jsonify({"code": "FAIL", "message": "wechat notify handler not wired"}), 501


@payment_bp.route("/api/payment/notify/alipay", methods=["POST"])
def alipay_notify():
    """支付宝异步通知占位。"""
    if not _alipay_configured():
        return "fail", 503
    return "fail", 501


@payment_bp.route("/api/payment/credits", methods=["GET"])
@login_required
def get_credits():
    """获取当前用户剩余额度"""
    from app import UserCredits

    credit = UserCredits.query.filter_by(user_id=current_user.id).first()
    return jsonify(
        {
            "credits": credit.credits if credit else 0,
            "total_purchased": credit.total_purchased if credit else 0,
        }
    )


@payment_bp.route("/api/payment/history", methods=["GET"])
@login_required
def payment_history():
    """当前用户支付/消耗记录（最近 N 条）。"""
    from app import PaymentHistory

    try:
        limit = int(request.args.get("limit") or "50")
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(200, limit))
    rows = (
        PaymentHistory.query.filter_by(user_id=current_user.id)
        .order_by(PaymentHistory.created_at.desc(), PaymentHistory.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "credits": r.credits,
                "amount": r.amount,
                "status": r.status,
                "session_id": r.stripe_session_id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            }
        )
    return jsonify({"items": items, "count": len(items)})


@payment_bp.route("/api/payment/use-credit", methods=["POST"])
@login_required
def use_credit():
    """消耗一次使用额度"""
    from app import UserCredits, db

    credit = UserCredits.query.filter_by(user_id=current_user.id).first()
    if not credit or credit.credits <= 0:
        return jsonify({"error": "额度不足，请购买订阅"}), 403

    credit.credits -= 1
    credit.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "remaining_credits": credit.credits})


def _record_pending_payment(
    user_id: int,
    plan_id: str,
    credits: int,
    amount: int,
    payment_id: str,
    provider: str,
):
    from app import PaymentHistory, db

    payment = PaymentHistory(
        user_id=user_id,
        plan_id=plan_id,
        credits=credits,
        amount=amount,
        stripe_session_id=f"{provider}:{payment_id}",
        status="pending",
    )
    db.session.add(payment)
    db.session.commit()


def _add_user_credits(
    user_id: int,
    credits: int,
    plan_id: str,
    payment_id: str,
    amount: int | None = None,
    provider: str = "stripe",
):
    """内部方法：为用户添加额度"""
    from app import PaymentHistory, UserCredits, db

    if amount is None:
        amount = SUBSCRIPTION_PLANS[plan_id]["price"]

    user_credit = UserCredits.query.filter_by(user_id=user_id).first()
    if user_credit:
        user_credit.credits += credits
        user_credit.total_purchased += credits
        user_credit.updated_at = datetime.utcnow()
    else:
        user_credit = UserCredits(
            user_id=user_id,
            credits=credits,
            total_purchased=credits,
        )
        db.session.add(user_credit)

    payment = PaymentHistory(
        user_id=user_id,
        plan_id=plan_id,
        credits=credits,
        amount=amount,
        stripe_session_id=f"{provider}:{payment_id}" if provider != "stripe" else payment_id,
        status="completed",
    )
    db.session.add(payment)
    db.session.commit()


def check_user_credits(user_id: int) -> bool:
    """检查用户是否有可用额度（供其他模块调用）"""
    from app import UserCredits

    credit = UserCredits.query.filter_by(user_id=user_id).first()
    return credit and credit.credits > 0


def agent_credits_enforced() -> bool:
    """Agent 是否强制扣额度。AGENT_SKIP_CREDITS=1 时跳过（本地调试）。"""
    raw = (os.getenv("AGENT_SKIP_CREDITS") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return False
    req = (os.getenv("AGENT_REQUIRE_CREDITS") or "1").strip().lower()
    return req not in ("0", "false", "no", "off")


def consume_user_credit(user_id: int) -> tuple[bool, int, str | None]:
    """
    消耗 1 次额度。返回 (ok, remaining, error_code)。
    error_code: insufficient | invalid_user | db_error
    """
    from app import UserCredits, db

    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, 0, "invalid_user"

    try:
        credit = UserCredits.query.filter_by(user_id=uid).first()
        if not credit:
            try:
                free_n = int((os.getenv("AGENT_FREE_CREDITS_ON_FIRST_USE") or "50").strip() or "0")
            except ValueError:
                free_n = 50
            if free_n > 0:
                credit = UserCredits(
                    user_id=uid,
                    credits=free_n,
                    total_purchased=0,
                )
                db.session.add(credit)
                db.session.flush()
            else:
                return False, 0, "insufficient"

        if credit.credits <= 0:
            return False, 0, "insufficient"

        credit.credits -= 1
        credit.updated_at = datetime.utcnow()
        try:
            from app import PaymentHistory

            db.session.add(
                PaymentHistory(
                    user_id=uid,
                    plan_id="agent_react",
                    credits=-1,
                    amount=0,
                    stripe_session_id=f"consume:{uid}:{int(datetime.utcnow().timestamp())}",
                    status="consumed",
                )
            )
        except Exception:
            pass
        db.session.commit()
        return True, int(credit.credits), None
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, 0, "db_error"
