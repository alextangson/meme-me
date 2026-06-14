"""背景杂乱根治门控 A/B：同脸同画风，唯一变量=梗的 action 文案（场景词 vs 改写后）。
before=旧文案（带悬崖/跑步机/问号增殖），after=改写后（场景→单道具、符号不增殖）。
构图宪法兜底句在两边都生效（=生产实况）；看 after 是否更干净且梗还在。
经免费 Gemini 中转站出图。手动跑。
"""
from pathlib import Path

from mememe.core.compiler import compile_meme
from mememe.core.schema import load_pack
from mememe.providers.gemini import GeminiProvider

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "patrol" / "gating-clutter"
# (pack, meme_idx, 旧 action, 画风)
CASES = [
    ("qimo", 3, "单手吊在悬崖边，崖上立着「60分」的牌子", "anime"),
    ("qimo", 4, "呆坐着，头顶问号越冒越多", "anime"),
    ("yundong", 6, "啃着蛋白棒朝后摆手拒绝，身后跑步机探出半个头", "anime"),
]


def main() -> None:
    ref = (ROOT / "out" / "demo" / "demo-face-f.png").read_bytes()
    provider = GeminiProvider()
    OUT.mkdir(parents=True, exist_ok=True)
    for pk, idx, old_action, style in CASES:
        pack = load_pack(ROOT / "packs" / f"{pk}.yaml")
        meme = pack.memes[idx]
        before_meme = meme.model_copy(update={"action": old_action})
        for label, m in (("before", before_meme), ("after", meme)):
            png = provider.generate(compile_meme(pack, m, style=style), ref)
            dest = OUT / f"{pk}-{meme.id}-{label}.png"
            dest.write_bytes(png)
            print(f"ok {pk}/{meme.id}/{label} -> {dest.relative_to(ROOT)} ({len(png)}B)")


if __name__ == "__main__":
    main()
