"""WeChat sticker spec post-processing.

WeChat custom stickers: 240×240. Chat re-encodes PNGs and drops transparency,
so we emit both transparent PNG and single-frame GIF and field-test which
survives import (DESIGN.md Stage 1).
"""

import io

from PIL import Image

try:  # iPhone 拍照默认 HEIC，注册后 PIL 才能解
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

STICKER_SIZE = 240
GIF_MAX_BYTES = 500 * 1024
SELFIE_MAX_EDGE = 1536  # 上传图归一化上限，省内存也够供应商用


def _open_rgba(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGBA")


def _fit_square(img: Image.Image) -> Image.Image:
    img.thumbnail((STICKER_SIZE, STICKER_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (STICKER_SIZE, STICKER_SIZE), (0, 0, 0, 0))
    offset = ((STICKER_SIZE - img.width) // 2, (STICKER_SIZE - img.height) // 2)
    canvas.paste(img, offset, img)
    return canvas


def to_sticker_png(image_bytes: bytes) -> bytes:
    canvas = _fit_square(_open_rgba(image_bytes))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_sticker_gif(image_bytes: bytes) -> bytes:
    canvas = _fit_square(_open_rgba(image_bytes))
    alpha = canvas.getchannel("A")
    # GIF has 1-bit transparency: quantize to 255 colors, reserve index 255
    paletted = canvas.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT)
    mask = alpha.point(lambda a: 255 if a < 128 else 0)
    paletted.paste(255, mask=mask)
    buf = io.BytesIO()
    paletted.save(buf, format="GIF", transparency=255, optimize=True)
    out = buf.getvalue()
    if len(out) > GIF_MAX_BYTES:
        raise ValueError(f"GIF exceeds WeChat limit: {len(out)} > {GIF_MAX_BYTES}")
    return out


def crop_to_faces(img: "Image.Image") -> "Image.Image":
    """放大人脸在参考图里的像素占比——脸部信号是相似度第一因子。

    半身/全身照里脸只占很小一块，模型拿到的面部信息太弱；裁到人脸
    周边（留足头发和肩膀）后相似度显著提升。Haar 检测不到脸
    （宠物照、侧脸、暗光）就原图直退，绝不误伤。
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img  # 没装 opencv 就跳过，裁剪是增强项不是依赖
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    # 两轮检测：先原灰度图；失败再直方图均衡兜底（弱光照片需要均衡，
    # 但大面积纯色背景下全局均衡反而会毁掉对比度——两轮都试才稳）
    detected = ()
    for g in (gray, cv2.equalizeHist(gray)):
        detected = cascade.detectMultiScale(
            g, scaleFactor=1.05, minNeighbors=5, minSize=(40, 40)
        )
        if len(detected):
            break
    if len(detected) == 0:
        return img
    # 滤掉误检：Haar 会把背景虚化点/衣褶认成小脸——只留面积达到
    # 最大脸 25% 的框（合照里真人脸尺寸相近，不会被误伤）
    max_area = max(int(w) * int(h) for x, y, w, h in detected)
    faces = [f for f in detected if int(f[2]) * int(f[3]) >= max_area * 0.25]
    # 所有人脸的并集框（合照都要进画面）
    x1 = min(int(x) for x, y, w, h in faces)
    y1 = min(int(y) for x, y, w, h in faces)
    x2 = max(int(x + w) for x, y, w, h in faces)
    y2 = max(int(y + h) for x, y, w, h in faces)
    # 扩边：横向 ~1.9x 留肩膀，纵向上 ~0.9x 留发型、下 ~1.3x 留上身
    fw, fh = x2 - x1, y2 - y1
    cx1 = max(0, x1 - int(fw * 0.45))
    cx2 = min(img.width, x2 + int(fw * 0.45))
    cy1 = max(0, y1 - int(fh * 0.9))
    cy2 = min(img.height, y2 + int(fh * 1.3))
    # 框几乎等于原图（本来就是特写）就不折腾
    if (cx2 - cx1) * (cy2 - cy1) > 0.9 * img.width * img.height:
        return img
    return img.crop((cx1, cy1, cx2, cy2))


def normalize_selfie(image_bytes: bytes) -> bytes:
    """把上传照片统一成下行安全的 JPEG：解 HEIC、人脸裁剪、削尺寸、剥 EXIF。

    非图片（伪装的文本/脚本）在这里被 PIL 拒掉，挡在生成管线之外。
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError("无法识别为图片") from e
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = crop_to_faces(img)
    if max(img.size) > SELFIE_MAX_EDGE:
        img.thumbnail((SELFIE_MAX_EDGE, SELFIE_MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def maybe_remove_background(image_bytes: bytes, *, enabled: bool) -> bytes:
    if not enabled:
        return image_bytes
    try:
        from rembg import remove
    except ImportError as e:
        raise RuntimeError(
            "背景移除需要可选依赖 rembg：uv sync --extra rembg"
        ) from e
    return remove(image_bytes)
