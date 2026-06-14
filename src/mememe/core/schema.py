"""Pack schema — the YAML meme-script format is this project's public API."""

import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

FREE_MEME_COUNT = 8

# caption 上限按显示宽度算（中文/全角=2，英文/半角=1）：中文仍 ~14 字，
# 但英文混排梗（"It works on my machine"=22）也装得下。240px 贴纸的可读上限。
CAPTION_MAX_WIDTH = 28


def caption_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _truncate_to_width(text: str, max_width: int) -> str:
    out: list[str] = []
    width = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > max_width:
            break
        out.append(ch)
        width += w
    return "".join(out).rstrip()


class Meme(BaseModel):
    id: str = Field(min_length=1)
    caption: str = Field(min_length=1)

    @field_validator("caption")
    @classmethod
    def _caption_within_width(cls, v: str) -> str:
        if caption_width(v) > CAPTION_MAX_WIDTH:
            raise ValueError(
                f"caption 显示宽度超过 {CAPTION_MAX_WIDTH}（中文算2/英文算1），请缩短"
            )
        return v

    expression: str = Field(min_length=1)
    action: str = Field(min_length=1)
    shot: str = Field(min_length=1)
    motion: str = ""  # 动图的运动描述；留空则由 action 推导


class Pack(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    version: int = 1
    language: str = "zh"
    subject: Literal["person", "pet", "group"] = "person"
    subject_desc: str = ""  # 主角外观描述，定制包用于无照片的风格预览
    style: str = Field(min_length=1)
    # 推荐画风（styles.py 的 id）：主题×合适画风的结合——用户没显式选画风时
    # 默认用它；留空 = 经典贴纸。画风弹窗里的显式选择永远优先。
    style_id: str = ""
    memes: list[Meme] = Field(min_length=1)

    @field_validator("memes")
    @classmethod
    def _unique_meme_ids(cls, memes: list[Meme]) -> list[Meme]:
        seen: set[str] = set()
        for meme in memes:
            if meme.id in seen:
                raise ValueError(f"duplicate meme id: {meme.id}")
            seen.add(meme.id)
        return memes

    @property
    def free_memes(self) -> list[Meme]:
        return self.memes[:FREE_MEME_COUNT]


def load_pack(path: Path | str) -> Pack:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Pack.model_validate(data)


def load_pack_lenient(path: Path | str) -> Pack:
    """供前端展示路径用：截断超宽 caption 而非抛异常，这样早期宽松规则
    存下的包（或任何老数据）被访问时不会 500。生成/CLI 仍走严格 load_pack。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for meme in (data or {}).get("memes") or []:
        cap = meme.get("caption")
        if isinstance(cap, str) and caption_width(cap) > CAPTION_MAX_WIDTH:
            meme["caption"] = _truncate_to_width(cap, CAPTION_MAX_WIDTH)
    return Pack.model_validate(data)
