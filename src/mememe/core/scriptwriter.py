"""对话式剧本策划 agent：聊天收集需求 → 产出经 schema 校验的定制剧本。

agent 只负责"梗的内容"；视觉风格基底由系统注入，保证定制包和官方包
走同一条一致性管线。这是个人定制和 B 端 IP 定制共用的地基。
"""

import json
from collections.abc import Callable

from pydantic import ValidationError

from mememe.core.schema import Pack

SYSTEM_PROMPT = """你是「表情星球」的金牌表情包策划，通过聊天帮用户把"想要的表情包主题"聊清楚。

你的每次回复都只输出一个 JSON 对象（不要任何其他文字）：
{"say":"你要说的话","options":["快捷选项"],"ready":false}
- say：口语化像朋友聊天，别列清单；每次最多问一个问题。
- options：0-4 个快捷选项（每个不超过 10 个字），用户点一下就等于回答。
  问题有典型答案时必须给选项；选项要具体、贴用户的上下文，猜得准比列得全重要；
  开放问题（比如问口头禅）也要给「没有，你来发挥」这类兜底选项，别逼用户打字。
- ready：信息够出方案就置 true，say 里招呼一句"信息够啦，给你出方案"即可。
  不要在聊天里输出完整方案，方案由系统按钮生成。

对话策略：
1. 想搞清楚的事：发给谁看（自用斗图/情侣/家人/同事群/粉丝群）、主角是谁
   （本人/宠物/吉祥物——之后用户会上传主角照片）、梗方向和语气、口头禅或黑话。
   但用户说过的、能从上下文推断的，绝不再问——每多问一个问题就流失一批用户。
2. 你是策划不是问卷：最多问 1-2 轮就要主动提案，把梗方向具体化成 2-4 个有
   画面感的选项放进 options 让用户挑（如「上班嘴替：表面收到内心崩溃」），
   别让用户凭空想。用户挑完方向通常就该 ready 了。
3. 用户点名品牌元素、吉祥物或 IP 角色时：你认识的（知名品牌/知名 IP）直接答应
   安排上就行，千万别问它长什么样——明知故问最劝退；只有你真不知道外观的
   小众角色（比如用户自家吉祥物），才顺嘴带一句，且要给示例降低回答成本，
   如「你们家小蓝大概是个啥造型？随口一说就行，比如『蓝色圆滚滚的小水滴』」。"""

DRAFT_INSTRUCTION = """基于以上全部对话，输出这套表情包剧本的 JSON（只输出 JSON，不要任何其他文字）：
{"id":"英文小写连字符id","name":"剧本名(2-6字)","description":"一句话描述",
"subject":"person或pet或group(多人合照)","subject_desc":"主角外观一句话(如：一只穿围裙的树懒玩偶/短发戴眼镜的程序员)",
"style_id":"从这个清单挑一个最配这套梗气质的画风：anime(日漫热血夸张)/doodle(团子涂鸦软萌)/shadiao(沙雕土味潦草)/mochi(3D手办软糯)/crayon(蜡笔童趣)/pop(波普撞色)/pixel(像素复古)/clay(黏土定格)/felt(羊毛毡手作)/bojack(美式扁平丧)/lineart(冷淡线条)/sticker(美式厚边贴纸)；拿不准就留空字符串",
"vibe":"一句话画风氛围(只准写：小道具、点缀符号、情绪关键词、配色点缀；不准写背景颜色/场景/环境——背景永远纯白)",
"memes":[{"id":"英文小写id","caption":"图内文案2-6字","expression":"具体可画的表情描述",
"action":"戏剧化的动作描述（用姿态和小型手持道具表达，不要写地点/房间/环境场景）",
"shot":"头肩特写或半身或全身"}]}
写梗铁律：
- caption 必须是聊天里会直接发出去的那句话（回应/情绪/吐槽，如「收到」「救我」「无语」
  的圈层化变体），不是标题也不是描述；用户在对话里给过的金句原样用作 caption。
- 一张图只讲一个笑点：每条 action 最多 1 个手持道具 + 1 个头顶符号，表情包只有
  240 像素大，元素堆多了就糊了；笑点靠表情和姿态，不靠道具数量。
- 用户点名要的元素（品牌图标/吉祥物/伙伴角色/特定道具）必须落实：写进 vibe，
  并出现在至少 6 条梗的 action 里；一律用画得出来的视觉语言描述外观
  （颜色+形状+材质，例：「一只橙色圆胖的简笔卡通小人」），不能只写品牌名——
  画图的模型不认识品牌名。
要求：memes 必须正好 16 个；前 8 个放用户最高频最想发的；
文案口语化、贴合对话里的真实语境和口头禅；表情和动作要具体、夸张、有画面感。"""

_STYLE_BASE = """Q版三头身（chibi）贴纸插画风格，粗白色描边，背景必须纯白。
严禁出现场景、房间、家具、风景等任何背景元素；地点和情境只用小型手持道具
或头顶符号示意，不画环境。
主体特征必须与参考照片一致并贯穿全套，整套形象完全一致。
表情夸张、动作戏剧化，微信表情包审美。
文案以大号中文手写体渲染在画面下方居中，字色深、带白边，清晰可读。"""

ChatFn = Callable[..., str]


def _build_style(vibe: str) -> str:
    style = _STYLE_BASE
    if vibe.strip():
        style += f"\n本套氛围：{vibe.strip()}"
    return style


def _parse_reply(raw: str) -> dict:
    """模型的结构化回复 → {say, options, ready, raw}。

    raw 原样保留进对话历史（模型下一轮能看到自己给过的选项）；
    格式不对就当纯文本聊——格式问题绝不能挡住对话。
    """
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if isinstance(data, dict):
        say = str(data.get("say", "")).strip()
        opts = data.get("options")
        if not isinstance(opts, list):
            opts = []
        options = list(dict.fromkeys(str(o).strip() for o in opts if str(o).strip()))[:4]
        if say:
            return {"say": say, "options": options, "ready": bool(data.get("ready")), "raw": raw}
    return {"say": raw, "options": [], "ready": False, "raw": raw}


class Scriptwriter:
    def __init__(self, chat: ChatFn):
        self._chat = chat

    def reply(self, history: list[dict]) -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        return _parse_reply(self._chat(messages, json_mode=True))

    def draft(self, history: list[dict]) -> Pack:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": DRAFT_INSTRUCTION},
        ]
        last_error: Exception | None = None
        for _ in range(2):
            raw = self._chat(messages, json_mode=True)
            try:
                data = json.loads(raw)
                data["style"] = _build_style(data.pop("vibe", ""))
                data.setdefault("language", "zh")
                # 编剧推荐画风：不在清单里的当没推荐（生成走经典）
                from mememe.core.styles import STYLES

                if data.get("style_id") not in STYLES:
                    data["style_id"] = ""
                return Pack.model_validate(data)
            except (ValueError, ValidationError) as e:
                last_error = e
                messages = messages + [
                    {"role": "assistant", "content": raw[:2000]},
                    {
                        "role": "user",
                        "content": f"上面的 JSON 校验失败：{str(e)[:300]}。"
                        "请修正后重新只输出 JSON。",
                    },
                ]
        raise ValueError(f"剧本生成失败，请再聊两句补充信息后重试：{last_error}")
