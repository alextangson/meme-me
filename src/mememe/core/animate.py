"""mp4 → WeChat-spec animated GIF (240×240, ≤500KB).

Quality ladder degrades fps/colors/duration until the size budget holds.
Requires ffmpeg on PATH.
"""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from mememe.core.postprocess import GIF_MAX_BYTES, STICKER_SIZE

# (fps, palette colors, max seconds, output px) — 逐级降级直到压进 500KB。
# 末几级降帧/降色/降分辨率：用户点了「动起来」，宁可糊一点也要出图，不该拿到报错。
_LADDER = [
    (12, 256, 5.0, STICKER_SIZE),
    (10, 128, 4.0, STICKER_SIZE),
    (8, 96, 3.0, STICKER_SIZE),
    (6, 64, 3.0, STICKER_SIZE),
    (6, 48, 2.5, STICKER_SIZE),
    (5, 40, 2.0, 220),
    (5, 32, 1.8, 192),
    (4, 24, 1.6, 160),
]

# 程序化动效：每个 effect 是一串 (dx, dy) 帧位移
_EFFECTS = {
    "shake": [(0, 0), (4, 2), (-3, -2), (2, -3)],
    "bounce": [(0, 0), (0, -6), (0, -10), (0, -5)],
}


def _quantize(frame: Image.Image, colors: int = 255) -> Image.Image:
    alpha = frame.getchannel("A")
    paletted = frame.convert("RGB").quantize(colors=min(colors, 255), method=Image.MEDIANCUT)
    mask = alpha.point(lambda a: 255 if a < 128 else 0)
    paletted.paste(255, mask=mask)
    return paletted


def frames_to_gif(
    frames: list[Image.Image],
    *,
    fps: int = 8,
    max_bytes: int = GIF_MAX_BYTES,
    colors: int = 255,
) -> bytes:
    paletted = [_quantize(f.convert("RGBA"), colors) for f in frames]
    buf = io.BytesIO()
    paletted[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=paletted[1:],
        duration=int(1000 / fps),
        loop=0,
        transparency=255,
        disposal=2,
    )
    out = buf.getvalue()
    if len(out) > max_bytes:
        raise ValueError(f"GIF exceeds {max_bytes} bytes")
    return out


def procedural_gif(png: bytes, *, effect: str = "shake", fps: int = 8) -> bytes:
    if effect not in _EFFECTS:
        raise ValueError(f"unknown effect: {effect}（可选：{'/'.join(_EFFECTS)}）")
    base = Image.open(io.BytesIO(png)).convert("RGBA")
    frames = []
    for dx, dy in _EFFECTS[effect]:
        canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
        canvas.paste(base, (dx, dy), base)
        frames.append(canvas)
    return frames_to_gif(frames, fps=fps)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def mp4_to_wechat_gif(
    mp4: bytes,
    *,
    size: int = STICKER_SIZE,
    max_bytes: int = GIF_MAX_BYTES,
    caption_source: bytes | None = None,
    caption_frac: float = 0.26,
) -> bytes:
    """Convert video to WeChat GIF.

    caption_source: the finished sticker PNG whose bottom strip (the rendered
    caption) gets alpha-pasted onto EVERY frame — video models animate text
    away after a frame or two, so the caption is pinned in post.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("动图转换需要 ffmpeg：brew install ffmpeg")

    caption_img = None
    if caption_source:
        caption_img = Image.open(io.BytesIO(caption_source)).convert("RGBA")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(mp4)
        for attempt, (fps, colors, dur, px) in enumerate(_LADDER):
            scale = f"scale={px}:{px}:flags=lanczos"
            frame_dir = Path(tmp) / f"frames{attempt}"
            frame_dir.mkdir()
            _ffmpeg(
                "-t", str(dur), "-i", str(src),
                "-vf", f"fps={fps},{scale}",
                str(frame_dir / "f_%04d.png"),
            )
            frames = [
                Image.open(p).convert("RGBA")
                for p in sorted(frame_dir.glob("f_*.png"))
            ]
            if not frames:
                raise RuntimeError("视频中提取不到帧")
            if caption_img is not None:
                # 文案条按当前级分辨率重算（视频模型几帧后就把字动没了，post 钉死）
                strip_top = int(px * (1 - caption_frac))
                strip = caption_img.resize((px, px)).crop((0, strip_top, px, px))
                for frame in frames:
                    frame.paste(strip, (0, strip_top), strip)
            try:
                return frames_to_gif(
                    frames, fps=fps, max_bytes=max_bytes, colors=colors
                )
            except ValueError:
                continue
    raise ValueError(f"GIF 压不进 {max_bytes} 字节，源视频太复杂")
