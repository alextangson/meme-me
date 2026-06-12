"""Compile a pack's meme script into per-image generation prompts.

Consistency strategy: every prompt carries the identical style block and the
same identity instruction, paired with the same reference photo at call time.
"""

from mememe.core.schema import Meme, Pack
from mememe.core.styles import CAPTION_STYLES, STYLES

# 只留深色经典款（用户拍板：彩色字体不好看）；想要彩色走显式 caption_style=cute
_CAPTION_VARIANTS = [
    "大号中文手写体，字色深、带白色描边，端正居中。",
    "超粗黑体大字，白色描边外加细黑外框，经典梗图字体，冲击力强。",
]

_IDENTITY_BLOCKS = {
    "person": """人物必须与参考照片中是同一个人：保持发型、脸型、肤色、眼镜/配饰、
服装等标志性特征，整套表情包中角色形象完全一致。
肤色必须自然、贴近参考照片的真实肤色（只做画风内的柔和风格化），
严禁蜡黄、橙黄、荧光色等不自然的整体偏色——周围的暖色道具和背景色
不得影响皮肤的颜色。""",
    "pet": """宠物必须与参考照片中是同一只：物种以参考照片为准（照片是狗就画狗、
是猫就画猫），严禁更换或混入其他动物；保持毛色、花纹、品种特征、体型、
项圈等配饰，整套表情包中形象完全一致，毛色忠实还原、严禁异常偏色。""",
    "group": """参考照片中的所有人都必须出现，并保持各自的标志性特征
（发型、脸型、肤色、眼镜/配饰、服装、相对身高体型），整套表情包中
每个人的形象完全一致，人物之间的互动关系生动自然。
每个人的肤色都要自然、贴近照片真实肤色，严禁蜡黄、荧光等不自然偏色。""",
}
_SUBJECT_WORD = {"person": "人物", "pet": "宠物", "group": "人物组合"}

_PROMPT_TEMPLATE = """\
基于参考照片中的{subject_word}，生成一张微信表情包贴纸。

【主体一致性】{identity}
无论什么画风，角色从头到脚都是同一种绘画/造型语言：脸部五官也必须按画风
重新绘制塑造，严禁出现照片质感的写实面孔、严禁把参考照片局部直接拼贴进画面——
相似度靠上述标志性特征的风格化再现达成，不靠照片复制。

【画幅与构图】正方形 1:1。角色居中、竖直端正不倾斜，主体占画面 70% 以上。
镜头景别严格按下方【本张内容】的「镜头」执行：特写让脸占大半；半身要带上手势；
全身要有完整姿态——任何景别下脸部都要五官清晰可辨，和参考照片的相似度是第一优先级。
动作和姿态要演出来：肢体语言夸张、有戏剧张力，这是表情包的灵魂。
画面只保留{subject_word}角色、下方内容里点名的道具与伙伴元素、以及文案；
绝对不要保留或重绘参考照片的背景，背景必须是纯白色——不要任何场景、房间、
家具、风景；若下方内容描述里出现地点或环境，只用小道具和姿态示意，不画环境。

【全局风格】
{style}

【本张内容】
- 表情：{expression}
- 动作：{action}
- 镜头：{shot}
- 画面文案（渲染在图内下方）：「{caption}」
"""


def compile_meme(
    pack: Pack,
    meme: Meme,
    caption_override: str | None = None,
    *,
    style: str | None = None,
    caption_style: str | None = None,
    caption_seed: int = 0,
    face_desc: str = "",
) -> str:
    prompt = _PROMPT_TEMPLATE.format(
        subject_word=_SUBJECT_WORD[pack.subject],
        identity=_IDENTITY_BLOCKS[pack.subject],
        style=pack.style.strip(),
        expression=meme.expression,
        action=meme.action,
        shot=meme.shot,
        caption=caption_override or meme.caption,
    )
    if style and style in STYLES:
        prompt += (
            "\n【画风指定】整体画风改为：" + STYLES[style]["block"]
            + "\n（画风以本节为准，上文与画风冲突的视觉描述按本节执行；"
            "主体一致性、居中端正的构图、纯白背景、白色描边、文案渲染要求保持不变。）"
        )
    if caption_style and caption_style in CAPTION_STYLES:
        prompt += "\n【文字样式】画面文案改用：" + CAPTION_STYLES[caption_style]["block"]
    else:
        # 文字风格一套一致（用户反馈：套内混排像拼凑）；种子按任务给，
        # 套与套之间仍有变化，同任务重摇/续生成稳定不换
        prompt += (
            "\n【文字样式】画面文案改用："
            + _CAPTION_VARIANTS[caption_seed % len(_CAPTION_VARIANTS)]
        )
    if face_desc:
        # 图像参考 + 文字特征双锚定：prompt 里点名的特征模型不敢丢
        prompt += (
            "\n【相貌特征锚点】参考照片主体的可辨识特征，生成时逐条对齐"
            "（按画风风格化呈现，但每一条都要看得出来）：\n" + face_desc
        )
    return prompt


def compile_pack(pack: Pack) -> list[str]:
    return [compile_meme(pack, meme) for meme in pack.memes]


_MOTION_TEMPLATE = """\
让画面中的卡通角色动起来：{motion}。
动作幅度适中、自然流畅、适合无缝循环播放。
镜头固定不动，背景保持纯白，角色形象和画面文案保持不变。"""


_KEYFRAME_TEMPLATE = """\
这是一张表情包贴纸。请生成同一张贴纸的下一个动画关键帧：
画风、角色、五官、构图、画面文字、背景全部保持完全不变，
只把动作微调到「{motion}」过程中的另一个瞬间（手臂/身体位置小幅变化即可）。
变化幅度必须小，确保两帧连续播放时形成自然的循环动画。"""


def compile_keyframe(
    pack: Pack, meme: Meme, motion_override: str | None = None
) -> str:
    motion = motion_override or meme.motion or meme.action
    return _KEYFRAME_TEMPLATE.format(motion=motion)


def compile_motion(
    pack: Pack, meme: Meme, motion_override: str | None = None
) -> str:
    motion = (
        motion_override
        or meme.motion
        or f"{meme.expression}，重复做出「{meme.action}」的动作"
    )
    return _MOTION_TEMPLATE.format(motion=motion)
