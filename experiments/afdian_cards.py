"""爱发电赞助方案卡 ×2（¥9.9 全套放开 / ¥29.9 专属定制）——正方形 1080。

品牌视觉复用晒图卡：躁动黄底、粗黑描边贴纸、弹跳阴影、明文网址。
PIL 确定性合成，不走生图模型——价格数字与中文必须像素级精确。
用法：.venv/bin/python experiments/afdian_cards.py  →  out/afdian/*.png
"""

from pathlib import Path

from PIL import Image, ImageDraw

from mememe.core.collage import (
    INK,
    ORANGE,
    WHITE,
    YELLOW,
    _brand_logo,
    _fit,
    _frame_sticker,
    _name_plaque,
    _paste_with_shadow,
)
from mememe.core.fonts import cjk_font as _font

S = 1080
PREVIEWS = Path("packs/previews")
OUT = Path("out/afdian")

SKUS = [
    {
        "file": "sku-9.9-quantao.png",
        "name": "全套放开",
        "price": "¥9.9",
        "perks": [
            "全套 16 张专属表情",
            "所有画风随便换 · 每天 10 套",
            "视频动图额度 +6 条",
        ],
        "samples": ["shechu", "style-anime", "lianai"],
    },
    {
        "file": "sku-29.9-dingzhi.png",
        "name": "专属定制",
        "price": "¥29.9",
        "perks": [
            "AI 编剧写你的专属主题",
            "含「全套放开」全部权益",
            "视频动图额度 +15 条",
        ],
        "samples": ["style-mochi", "style-pixel", "gouzi"],
    },
]

# 贴纸散落参数：固定旋转/抖动，确定性输出
ROTS = (-5, 4, -3)
JITS = ((0, 8), (0, -6), (0, 10))


def _accents_sq(draw: ImageDraw.ImageDraw) -> None:
    """四角橙色点缀，按 1080 方形画布定位。"""
    for cx, cy, r in ((1000, 170, 12), (70, 230, 9), (1010, 950, 10), (62, 880, 13)):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ORANGE)
    for cx, cy, r in ((945, 100, 22), (115, 985, 18)):
        draw.polygon(
            [(cx, cy - r), (cx + r // 3, cy - r // 3), (cx + r, cy), (cx + r // 3, cy + r // 3),
             (cx, cy + r), (cx - r // 3, cy + r // 3), (cx - r, cy), (cx - r // 3, cy - r // 3)],
            fill=ORANGE,
        )


def build_card(sku: dict) -> Image.Image:
    canvas = Image.new("RGBA", (S, S), YELLOW)
    draw = ImageDraw.Draw(canvas)
    _accents_sq(draw)

    # 顶部品牌区 + SKU 名贴纸牌
    canvas.alpha_composite(_brand_logo(96), (52, 36))
    draw.text((164, 58), "表情星球", fill=INK, font=_font(46),
              stroke_width=1, stroke_fill=INK)
    plaque = _name_plaque(sku["name"]).rotate(2.5, resample=Image.BICUBIC, expand=True)
    _paste_with_shadow(canvas, plaque, ((S - plaque.width) // 2, 142))

    # 大价格：橙色 + 白描边，冲动消费要一眼看到数
    font = _font(170)
    tw = draw.textlength(sku["price"], font=font)
    draw.text(((S - tw) // 2, 268), sku["price"], fill=ORANGE, font=font,
              stroke_width=10, stroke_fill=WHITE)

    # 权益清单：白底贴纸卡居中
    font = _font(40)
    widest = max(int(draw.textlength(p, font=font)) for p in sku["perks"])
    pad_x, line_h = 56, 64
    box_w = widest + pad_x * 2 + 56
    box_h = line_h * len(sku["perks"]) + 48
    card = Image.new("RGBA", (box_w + 10, box_h + 10), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((5, 5, box_w + 5, box_h + 5), radius=28,
                         fill=WHITE, outline=INK, width=5)
    for i, perk in enumerate(sku["perks"]):
        y = 28 + i * line_h
        cd.text((pad_x, y), "✓", fill=ORANGE, font=font)
        cd.text((pad_x + 56, y), perk, fill=INK, font=font)
    _paste_with_shadow(canvas, card, ((S - card.width) // 2, 488))

    # 贴纸样片散落：真实产品产出，所见即所得
    tile_y = 760
    cell = S // 3
    for i, pid in enumerate(sku["samples"]):
        tile = Image.open(PREVIEWS / f"{pid}.png").convert("RGBA")
        framed = _frame_sticker(_fit(tile, 216))
        rotated = framed.rotate(ROTS[i], resample=Image.BICUBIC, expand=True)
        jx, jy = JITS[i]
        x = i * cell + (cell - rotated.width) // 2 + jx
        _paste_with_shadow(canvas, rotated, (x, tile_y + jy))

    # 底部：发货说明 + 站点
    font = _font(34)
    note = "付款后秒发兑换码 · 站内输入立即生效"
    tw = draw.textlength(note, font=font)
    draw.text(((S - tw) // 2, 1014), note, fill=INK, font=font,
              stroke_width=5, stroke_fill=WHITE)
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for sku in SKUS:
        path = OUT / sku["file"]
        build_card(sku).convert("RGB").save(path, format="PNG", optimize=True)
        print(path)


if __name__ == "__main__":
    main()
