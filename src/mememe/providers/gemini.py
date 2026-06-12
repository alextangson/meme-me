"""Gemini image provider (BYOK). Needs GEMINI_API_KEY or GOOGLE_API_KEY.

注意：Gemini API 在中国大陆不可直连，需要网络代理（见 docs/DESIGN.md）。
"""

import os
from typing import Any

DEFAULT_MODEL = "gemini-3.1-flash-image"
VISION_MODEL = "gemini-2.5-flash"


def describe_subject(reference: bytes) -> str:
    """提取参考照片主体的可辨识外观特征文字——注入生成 prompt 做锚点。

    图像参考 + 文字特征双锚定，相似度比纯图参考稳得多（模型会忽略
    图里的细节，但不会忽略 prompt 里点名的特征）。任何失败返回空串：
    特征注入是增强项，绝不挡生成。
    """
    try:
        from google import genai
        from google.genai import types

        kwargs: dict[str, Any] = {}
        base_url = os.environ.get("MEMEME_GEMINI_BASE_URL")
        if base_url:
            kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        client = genai.Client(**kwargs)
        mime = (
            "image/png"
            if reference[:8] == b"\x89PNG\r\n\x1a\n"
            else "image/jpeg"
        )
        resp = client.models.generate_content(
            model=os.environ.get("MEMEME_VISION_MODEL", VISION_MODEL),
            contents=[
                types.Part.from_bytes(data=reference, mime_type=mime),
                "用4-6条简短要点客观描述照片主体（人物或宠物）的可辨识外观特征："
                "脸型、发型发色、眉眼、鼻唇、眼镜或饰品、胡须痣等显著特征"
                "（宠物则是品种、毛色花纹、五官特点）。每条不超过15个字。"
                "只描述长相和穿着佩饰这类稳定特征；不要描述表情、动作、姿态、"
                "手里拿的东西和背景。不要主观评价，直接输出要点列表。",
            ],
        )
        return (resp.text or "").strip()[:500]
    except Exception:
        return ""


def extract_image_bytes(response: Any) -> bytes:
    texts: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                return inline.data
            if getattr(part, "text", None):
                texts.append(part.text)
    detail = "; ".join(texts) or "empty response"
    raise RuntimeError(f"Gemini returned no image: {detail}")


class GeminiProvider:
    def __init__(self, model: str | None = None):
        from google import genai

        kwargs: dict[str, Any] = {}
        base_url = os.environ.get("MEMEME_GEMINI_BASE_URL")
        if base_url:
            from google.genai import types

            kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        # api key read from GEMINI_API_KEY / GOOGLE_API_KEY env
        self._client = genai.Client(**kwargs)
        self._model = model or os.environ.get(
            "MEMEME_GEMINI_MODEL", DEFAULT_MODEL
        )

    def generate(self, prompt: str, reference: bytes) -> bytes:
        from google.genai import types

        mime = (
            "image/png"
            if reference[:8] == b"\x89PNG\r\n\x1a\n"
            else "image/jpeg"
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=reference, mime_type=mime),
                prompt,
            ],
            config=types.GenerateContentConfig(
                image_config=types.ImageConfig(aspect_ratio="1:1")
            ),
        )
        return extract_image_bytes(response)
