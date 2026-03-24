# agents/vision_describe.py
"""
通用视觉描述服务：使用视觉模型将图片转为文本描述，供业务模型使用。

支持多种场景：
- 通用图片描述：根据用户意图灵活描述图片内容
- 原型图 → 测试用例：针对 UI 原型图输出结构化描述（核心场景之一）
- 可扩展更多场景：报错截图分析、流程图识别等
"""

import os
from typing import Optional

from config import Config

# 场景：原型图 → 测试用例（核心能力之一）
PROMPT_PROTOTYPE_TESTCASE = """你是一个 UI 原型图分析助手。用户上传了一张原型图，需要根据它生成测试用例。

请按以下结构描述图片内容：
1. **页面类型**：如登录页、列表页、表单页等
2. **可交互元素**：
   - 类型（按钮/输入框/链接/下拉/单选/多选等）
   - 位置/顺序
   - 文案或占位符
3. **业务流程**：用户可能进行的操作路径
4. **注意事项**：如必填项、校验规则等（如有）

输出要求：清晰、结构化，便于后续模型生成测试用例。"""


def _call_vision_api(image_base64: str, prompt: str, user_intent: str = "") -> str:
    """
    调用 DashScope 视觉模型（qwen3.5-plus 支持图像）。
    使用 OpenAI 兼容接口。
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("请安装 openai: pip install openai")

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", "")
    if not api_key:
        raise ValueError("未配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY")

    url = image_base64
    if not url.startswith("data:"):
        url = f"data:image/png;base64,{image_base64}" if "base64" not in image_base64 else image_base64

    full_prompt = prompt
    if user_intent:
        full_prompt += f"\n\n用户补充说明：{user_intent}"

    base = getattr(Config, "DASHSCOPE_COMPAT_BASE_URL", None) or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    client = OpenAI(api_key=api_key, base_url=base.rstrip("/"))

    response = client.chat.completions.create(
        model="qwen3.5-plus",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": full_prompt},
                ],
            }
        ],
        max_tokens=2048,
    )

    if response.choices and len(response.choices) > 0:
        return (response.choices[0].message.content or "").strip()
    return ""


class VisionDescribeService:
    """
    通用视觉描述服务：根据用户意图和场景，调用视觉模型生成图片描述。

    核心能力包括但不限于：
    - 通用图片描述（describe_image）
    - 原型图 → 测试用例（describe_prototype_for_testcase）
    """

    def __init__(self, vision_model: str = "qwen3.5-plus"):
        self.vision_model = vision_model

    def describe_image(
        self,
        image_base64: str,
        user_intent: str = "",
        context: str = "",
    ) -> str:
        """
        通用图片描述：根据用户意图灵活描述图片内容。
        - user_intent: 用户输入，用于引导描述侧重点（如「分析界面布局」「提取文字」）
        - context: 可选上下文，如「当前项目为 XX，请重点描述与测试相关的元素」
        """
        prompt = "请详细、准确地描述这张图片的内容，包括：可识别的文字、布局结构、关键元素、视觉层次等。根据用户的补充说明调整描述侧重点。"
        if context:
            prompt += f"\n\n上下文：{context}"
        return _call_vision_api(image_base64, prompt, user_intent)

    def describe_prototype_for_testcase(
        self, image_base64: str, user_intent: str = "", locale: Optional[str] = None
    ) -> str:
        """场景：原型图 → 测试用例。针对 UI 原型图输出结构化描述，便于生成测试用例。"""
        from .locale_prompts import vision_prototype_prompt

        return _call_vision_api(image_base64, vision_prototype_prompt(locale), user_intent)
