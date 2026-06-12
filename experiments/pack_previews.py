"""主题预览图重生成：女生示例脸 × 各主题的推荐画风（pack.style_id）。

预览图是用户对主题的第一眼，必须与真实生成一致：同一条管线、
同一个推荐画风、取每个主题的第一条梗（约定 = sendability 最高）。
宠物包（用宠物照）与情侣包（用合照）不在此列，单独维护。

烧真实 API 额度——只在画风/模板/示例脸变更后手动重跑。
用法（在带 key 的终端里跑）:
    .venv/bin/python experiments/pack_previews.py            # 全部人类单人主题
    .venv/bin/python experiments/pack_previews.py yundong    # 只跑指定主题
"""

import importlib.util
import os
import sys
from pathlib import Path

from mememe.core.compiler import compile_meme
from mememe.core.postprocess import maybe_remove_background, to_sticker_png
from mememe.core.schema import load_pack

ROOT = Path(__file__).parent.parent
DEFAULT_FACE = ROOT / "out" / "demo" / "demo-face-f.png"
HUMAN_PACKS = ["shechu", "yundong", "yinyang", "lianai", "ganfan", "qimo", "hajimi"]


def _provider_chain():
    from mememe.providers.gemini import GeminiProvider

    chain = [("gemini", GeminiProvider())]
    try:
        from mememe.providers.seedream import SeedreamProvider

        chain.append(("seedream", SeedreamProvider()))
    except RuntimeError:
        pass  # 没配 ARK_API_KEY 就不挂兜底
    return chain


def main() -> None:
    pack_ids = sys.argv[1:] or HUMAN_PACKS
    reference = Path(os.environ.get("MEMEME_PREVIEW_FACE", DEFAULT_FACE)).read_bytes()
    rembg_on = importlib.util.find_spec("rembg") is not None
    chain = _provider_chain()
    failed = []
    for pid in pack_ids:
        pack = load_pack(ROOT / "packs" / f"{pid}.yaml")
        meme = pack.memes[0]
        prompt = compile_meme(
            pack, meme, style=pack.style_id or None, caption_seed=3
        )
        raw = None
        for name, provider in chain:
            try:
                raw = provider.generate(prompt, reference)
                break
            except Exception as e:
                print(f"!! {pid} via {name}: {type(e).__name__}: {e}")
        if raw is None:
            failed.append(pid)
            continue
        png = to_sticker_png(maybe_remove_background(raw, enabled=rembg_on))
        dest = ROOT / "packs" / "previews" / f"{pid}.png"
        dest.write_bytes(png)
        print(f"ok {pid} ({pack.style_id or 'classic'}) -> {dest.relative_to(ROOT)}")
    if failed:
        sys.exit(f"未完成: {', '.join(failed)}（重跑这几个即可）")


if __name__ == "__main__":
    main()
