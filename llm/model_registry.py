from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ModelPricing:
    """
    价格单位：每 1,000,000 tokens（百万 token）。
    - input_per_million / output_per_million: 数值（可为 None 表示未知/未配置）
    - currency: 货币符号/缩写（如 CNY/USD），仅展示用途
    """

    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None
    currency: str = "CNY"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    provider: str  # qwen / qianfan / zhipu / deepseek ...
    enabled: bool = True
    vision: bool = False
    context_length: Optional[int] = None
    pricing: ModelPricing = ModelPricing()
    priority: int = 0  # Auto 选模：值越大越优先

    def to_public_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # 兼容前端：pricing 展开为对象
        return d


def _env_float(key: str) -> Optional[float]:
    v = os.getenv(key)
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n"):
        return False
    return default


def _enabled(model_id: str, *, default: bool) -> bool:
    """
    模型启用开关：用环境变量精确控制“下拉框出现 + 后端允许透传 + Auto 候选”。
    约定：
      MODEL_ENABLE__<MODEL_ID_UPPER>=1/0
    例：
      MODEL_ENABLE__QWEN2.5-VL-MAX=1
    """
    mid = str(model_id).strip().upper()
    return _env_bool(f"MODEL_ENABLE__{mid}", default=default)


def _price_for(model_id: str, *, currency: str = "CNY") -> ModelPricing:
    """
    支持用环境变量覆盖价格，便于你接入 DeepSeek/调整计费而无需改代码。
    约定：
      - MODEL_PRICE__<MODEL_ID_UPPER>__IN_PER_MILLION
      - MODEL_PRICE__<MODEL_ID_UPPER>__OUT_PER_MILLION
      - MODEL_PRICE__<MODEL_ID_UPPER>__CURRENCY
    例如：
      MODEL_PRICE__QWEN2.5-VL-PLUS__IN_PER_MILLION=12.5
      MODEL_PRICE__QWEN2.5-VL-PLUS__OUT_PER_MILLION=50
      MODEL_PRICE__QWEN2.5-VL-PLUS__CURRENCY=CNY
    """
    mid = str(model_id).strip().upper()
    cur = (os.getenv(f"MODEL_PRICE__{mid}__CURRENCY") or currency or "CNY").strip() or "CNY"
    in_p = _env_float(f"MODEL_PRICE__{mid}__IN_PER_MILLION")
    out_p = _env_float(f"MODEL_PRICE__{mid}__OUT_PER_MILLION")
    return ModelPricing(input_per_million=in_p, output_per_million=out_p, currency=cur)


def _build_registry() -> List[ModelSpec]:
    """
    单一真相来源：所有可在前端下拉框出现的模型都在这里登记。
    说明：
    - 价格是“百万 token”口径，便于展示；如果暂时不确定可以先填 None。
    - DeepSeek 先登记但可 disabled，待你接入 provider 后再启用。
    """

    return [
        # ---- Qwen (DashScope compatible-mode) ----
        ModelSpec(
            id="qwen3.5-plus",
            label="Qwen-3.5-Plus",
            provider="qwen",
            enabled=_enabled("qwen3.5-plus", default=True),
            vision=True,  # 你当前项目里把它当作可发图模型使用
            pricing=_price_for("qwen3.5-plus"),
            priority=60,
        ),
        ModelSpec(
            id="qwen3.6-flash",
            label="Qwen-3.6-Flash",
            provider="qwen",
            enabled=_enabled("qwen3.6-flash", default=True),
            vision=False,
            pricing=_price_for("qwen3.6-flash"),
            priority=58,
        ),
        ModelSpec(
            id="qwen3.6-plus",
            label="Qwen-3.6-Plus",
            provider="qwen",
            enabled=_enabled("qwen3.6-plus", default=True),
            vision=True,
            pricing=_price_for("qwen3.6-plus"),
            priority=62,
        ),
        ModelSpec(
            id="qwen-max-thinking",
            label="Qwen-Max (auto thinking)",
            provider="qwen",
            # 默认不出现在下拉框（效果差）；需要时 MODEL_ENABLE__QWEN-MAX-THINKING=1
            enabled=_enabled("qwen-max-thinking", default=False),
            vision=False,
            pricing=_price_for("qwen-max-thinking"),
            priority=50,
        ),
        # ---- Zhipu (GLM) ----
        ModelSpec(
            id="glm-4-flash",
            label="GLM-4-Flash",
            provider="zhipu",
            enabled=_enabled("glm-4-flash", default=False),
            vision=False,
            pricing=_price_for("glm-4-flash"),
            priority=30,
        ),
        ModelSpec(
            id="glm-5",
            label="GLM-5",
            provider="zhipu",
            enabled=_enabled("glm-5", default=True),
            vision=False,
            pricing=_price_for("glm-5"),
            priority=35,
        ),
        # ---- DeepSeek (placeholder for future integration) ----
        ModelSpec(
            id="deepseek-v3",
            label="DeepSeek-V3",
            provider="deepseek",
            enabled=_enabled("deepseek-v3", default=False),
            vision=False,
            pricing=_price_for("deepseek-v3"),
            priority=55,
        ),
        ModelSpec(
            id="deepseek-r1",
            label="DeepSeek-R1",
            provider="deepseek",
            enabled=_enabled("deepseek-r1", default=False),
            vision=False,
            pricing=_price_for("deepseek-r1"),
            priority=65,
        ),
        ModelSpec(
            id="deepseek-v4-pro",
            label="DeepSeek-V4-Pro",
            provider="deepseek",
            # 与 Qwen/文心等一致：默认出现在下拉框；若需隐藏可设 MODEL_ENABLE__DEEPSEEK-V4-PRO=0
            enabled=_enabled("deepseek-v4-pro", default=True),
            vision=False,
            context_length=128_000,
            pricing=_price_for("deepseek-v4-pro"),
            priority=68,
        ),
        ModelSpec(
            id="deepseek-v4-flash",
            label="DeepSeek-V4-Flash",
            provider="deepseek",
            enabled=_enabled("deepseek-v4-flash", default=True),
            vision=False,
            context_length=128_000,
            pricing=_price_for("deepseek-v4-flash"),
            priority=66,
        ),
    ]


_REGISTRY: List[ModelSpec] = _build_registry()
_BY_ID: Dict[str, ModelSpec] = {m.id: m for m in _REGISTRY}


def list_models(*, include_disabled: bool = False) -> List[ModelSpec]:
    if include_disabled:
        return list(_REGISTRY)
    return [m for m in _REGISTRY if m.enabled]


def get_model(model_id: str) -> Optional[ModelSpec]:
    if not model_id:
        return None
    return _BY_ID.get(str(model_id).strip())


def is_supported_model(model_id: str) -> bool:
    m = get_model(model_id)
    return bool(m and m.enabled)


def supports_vision(model_id: str) -> bool:
    m = get_model(model_id)
    return bool(m and m.vision)


def _total_price_per_million(m: ModelSpec) -> float:
    """Auto 选模：成本越低越优先（百万 token 口径）；缺失则视为最贵。"""
    p = m.pricing or ModelPricing()
    if p.input_per_million is None or p.output_per_million is None:
        return float("inf")
    try:
        return float(p.input_per_million) + float(p.output_per_million)
    except Exception:
        return float("inf")


def choose_auto_model(*, has_images: bool) -> Optional[str]:
    """
    Auto 选模（兼容旧调用方）。新代码请用 llm.model_router.resolve_request_model。
    """
    from .model_scheduler import choose_auto_model as _choose

    cost_policy = "quality_first" if has_images else "balanced"
    return _choose(has_images=has_images, cost_policy=cost_policy)


def reload_registry() -> None:
    """环境变量变更后重建注册表与调度缓存。"""
    global _REGISTRY, _BY_ID
    _REGISTRY = _build_registry()
    _BY_ID = {m.id: m for m in _REGISTRY}
    from . import model_scheduler

    model_scheduler.refresh_scheduler_cache()

