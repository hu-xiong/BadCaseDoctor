# routers/payment.py
"""
Stripe 订阅支付模块
支持4个档位：$20/40/60/100 对应不同使用次数
"""

import stripe
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
import os

payment_bp = Blueprint('payment', __name__)

# Stripe 配置
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_xxx')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_xxx')

# 订阅计划配置
SUBSCRIPTION_PLANS = {
    'basic': {
        'name': 'Basic Plan',
        'price': 2000,  # $20.00 (单位：美分)
        'credits': 100,  # 使用次数
        'description': '100 次使用额度'
    },
    'standard': {
        'name': 'Standard Plan',
        'price': 4000,  # $40.00
        'credits': 250,
        'description': '250 次使用额度'
    },
    'professional': {
        'name': 'Professional Plan',
        'price': 6000,  # $60.00
        'credits': 500,
        'description': '500 次使用额度'
    },
    'enterprise': {
        'name': 'Enterprise Plan',
        'price': 10000,  # $100.00
        'credits': 1200,
        'description': '1200 次使用额度'
    }
}


@payment_bp.route('/api/payment/plans', methods=['GET'])
def get_plans():
    """获取所有订阅计划"""
    plans = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        plans.append({
            'id': plan_id,
            'name': plan['name'],
            'price': plan['price'] / 100,  # 转换为美元
            'credits': plan['credits'],
            'description': plan['description']
        })
    return jsonify({'plans': plans})


@payment_bp.route('/api/payment/create-checkout', methods=['POST'])
@login_required
def create_checkout():
    """创建 Stripe Checkout 会话"""
    data = request.json
    plan_id = data.get('plan_id')
    
    if plan_id not in SUBSCRIPTION_PLANS:
        return jsonify({'error': '无效的订阅计划'}), 400
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    try:
        # 创建 Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': plan['name'],
                        'description': plan['description'],
                    },
                    'unit_amount': plan['price'],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{request.host_url}payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{request.host_url}payment/cancel",
            metadata={
                'user_id': str(current_user.id),
                'plan_id': plan_id,
                'credits': str(plan['credits'])
            },
            customer_email=current_user.email
        )
        
        return jsonify({
            'checkout_url': session.url,
            'session_id': session.id
        })
    
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500


@payment_bp.route('/api/payment/webhook', methods=['POST'])
def webhook():
    """Stripe Webhook 回调处理"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        return 'Invalid signature', 400
    
    # 处理支付成功事件
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        user_id = int(session['metadata']['user_id'])
        plan_id = session['metadata']['plan_id']
        credits = int(session['metadata']['credits'])
        
        # 更新用户额度
        _add_user_credits(user_id, credits, plan_id, session['id'])
        
        print(f"[PAYMENT] ✅ 用户 {user_id} 购买 {plan_id}，增加 {credits} 次额度")
    
    return '', 200


@payment_bp.route('/api/payment/credits', methods=['GET'])
@login_required
def get_credits():
    """获取当前用户剩余额度"""
    from app import db, UserCredits
    
    credit = UserCredits.query.filter_by(user_id=current_user.id).first()
    
    return jsonify({
        'credits': credit.credits if credit else 0,
        'total_purchased': credit.total_purchased if credit else 0
    })


@payment_bp.route('/api/payment/use-credit', methods=['POST'])
@login_required
def use_credit():
    """消耗一次使用额度"""
    from app import db, UserCredits
    
    credit = UserCredits.query.filter_by(user_id=current_user.id).first()
    
    if not credit or credit.credits <= 0:
        return jsonify({'error': '额度不足，请购买订阅'}), 403
    
    credit.credits -= 1
    credit.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'remaining_credits': credit.credits
    })


def _add_user_credits(user_id: int, credits: int, plan_id: str, payment_id: str):
    """内部方法：为用户添加额度"""
    from app import db, UserCredits, PaymentHistory
    
    # 更新或创建用户额度
    user_credit = UserCredits.query.filter_by(user_id=user_id).first()
    if user_credit:
        user_credit.credits += credits
        user_credit.total_purchased += credits
        user_credit.updated_at = datetime.utcnow()
    else:
        user_credit = UserCredits(
            user_id=user_id,
            credits=credits,
            total_purchased=credits
        )
        db.session.add(user_credit)
    
    # 记录支付历史
    payment = PaymentHistory(
        user_id=user_id,
        plan_id=plan_id,
        credits=credits,
        amount=SUBSCRIPTION_PLANS[plan_id]['price'],
        stripe_session_id=payment_id,
        status='completed'
    )
    db.session.add(payment)
    
    db.session.commit()


def check_user_credits(user_id: int) -> bool:
    """检查用户是否有可用额度（供其他模块调用）"""
    from app import UserCredits
    
    credit = UserCredits.query.filter_by(user_id=user_id).first()
    return credit and credit.credits > 0
