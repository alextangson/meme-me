"""item-3 门控 A/B：同脸同梗同画风，唯一变量=构图宪法的「漫画特效不铺满」条款。
左=条款生效(after)，右=剥掉条款(before)。验证：收紧背景没削掉热血能量感。
经免费 Gemini 中转站出图（与生产同管线）。手动跑，别挂 CI。
"""
import re
from pathlib import Path

from mememe.core.compiler import compile_meme
from mememe.core.schema import load_pack
from mememe.providers.gemini import GeminiProvider

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "patrol" / "gating-item3"
CLAUSE = re.compile(r"\n漫画特效（速度线.*?体积上限）。", re.S)


def main() -> None:
    pack = load_pack(ROOT / "packs" / "yundong.yaml")
    ref = (ROOT / "out" / "demo" / "demo-face-f.png").read_bytes()
    provider = GeminiProvider()
    OUT.mkdir(parents=True, exist_ok=True)
    for idx in (1, 2):  # 双腿抖成波浪线 / 双手抖成残影——天然招漫画特效
        meme = pack.memes[idx]
        after = compile_meme(pack, meme, style="anime")
        before = CLAUSE.sub("", after)
        assert before != after, "item-3 clause not found in prompt"
        for label, prompt in (("after", after), ("before", before)):
            png = provider.generate(prompt, ref)
            dest = OUT / f"anime-{meme.id}-{label}.png"
            dest.write_bytes(png)
            print(f"ok anime/{meme.id}/{label} -> {dest.relative_to(ROOT)} ({len(png)}B)")


if __name__ == "__main__":
    main()
