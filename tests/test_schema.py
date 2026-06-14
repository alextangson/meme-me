from pathlib import Path

import pytest
from pydantic import ValidationError

from mememe.core.schema import (
    CAPTION_MAX_WIDTH,
    Pack,
    caption_width,
    load_pack,
    load_pack_lenient,
)

PACKS_DIR = Path(__file__).parent.parent / "packs"


def test_load_shechu_pack():
    pack = load_pack(PACKS_DIR / "shechu.yaml")
    assert pack.id == "shechu"
    assert pack.name == "社畜的一天"
    assert len(pack.memes) == 16
    assert pack.style.strip()


def test_every_meme_has_required_fields():
    pack = load_pack(PACKS_DIR / "shechu.yaml")
    for meme in pack.memes:
        assert meme.id.strip()
        assert meme.caption.strip()
        assert meme.expression.strip()
        assert meme.action.strip()
        assert meme.shot.strip()


def test_free_memes_is_first_eight():
    pack = load_pack(PACKS_DIR / "shechu.yaml")
    assert len(pack.free_memes) == 8
    assert pack.free_memes == pack.memes[:8]
    assert pack.free_memes[0].caption == "收到"


def _minimal_pack_dict():
    return {
        "id": "t",
        "name": "测试",
        "style": "风格",
        "memes": [
            {
                "id": "a",
                "caption": "好",
                "expression": "笑",
                "action": "站",
                "shot": "半身",
            }
        ],
    }


def test_duplicate_meme_ids_rejected():
    data = _minimal_pack_dict()
    data["memes"].append(dict(data["memes"][0]))
    with pytest.raises(ValidationError, match="duplicate"):
        Pack.model_validate(data)


def test_missing_caption_rejected():
    data = _minimal_pack_dict()
    del data["memes"][0]["caption"]
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_overlong_caption_rejected():
    """240px 贴纸印不下长句——定制出稿跑飞的文案要在 schema 层拦住（会触发重试修正）。"""
    data = _minimal_pack_dict()
    data["memes"][0]["caption"] = "这句话实在是太长了根本印不到表情包上"  # 18 字
    with pytest.raises(ValidationError):
        Pack.model_validate(data)
    data["memes"][0]["caption"] = "oncall中，勿cue"  # 12 字，门控过的官方包上限
    assert Pack.model_validate(data).memes[0].caption == "oncall中，勿cue"


def test_caption_width_counts_cjk_double():
    assert caption_width("好") == 2  # 中文全角=2
    assert caption_width("ok") == 2  # 两个 ASCII=2
    assert caption_width("It works on my machine") == 22


def test_english_caption_accepted_by_display_width():
    """英文/混排梗（经典程序员梗）按显示宽度计，旧的 14 字上限会误杀。"""
    data = _minimal_pack_dict()
    data["memes"][0]["caption"] = "It works on my machine"  # 22 宽 ≤ 28
    assert Pack.model_validate(data).memes[0].caption == "It works on my machine"
    data["memes"][0]["caption"] = "不是 bug，是 feature"  # 混排，旧规则超 14 字
    assert Pack.model_validate(data).memes[0].caption == "不是 bug，是 feature"


def test_overwidth_cjk_caption_still_rejected():
    data = _minimal_pack_dict()
    data["memes"][0]["caption"] = "一二三四五六七八九十一二三四五"  # 15 CJK = 30 宽 > 28
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_load_pack_lenient_repairs_overwidth_caption(tmp_path):
    """早期宽松规则存下的超宽 caption：宽松加载截断兜底、绝不抛异常（读路径防 500）。"""
    import yaml

    data = _minimal_pack_dict()
    data["memes"][0]["caption"] = "这是一句一定会超出显示宽度上限的特别长的废话文案"
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError):  # 严格加载仍抛
        load_pack(p)
    pack = load_pack_lenient(p)  # 宽松加载兜底
    assert caption_width(pack.memes[0].caption) <= CAPTION_MAX_WIDTH
    assert pack.memes[0].caption  # 截断后仍非空


def test_empty_memes_rejected():
    data = _minimal_pack_dict()
    data["memes"] = []
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_meme_motion_field_optional_with_default():
    data = _minimal_pack_dict()
    pack = Pack.model_validate(data)
    assert pack.memes[0].motion == ""
    data["memes"][0]["motion"] = "敬礼的手上下挥动"
    pack = Pack.model_validate(data)
    assert pack.memes[0].motion == "敬礼的手上下挥动"


def test_subject_defaults_to_person_and_accepts_pet():
    data = _minimal_pack_dict()
    assert Pack.model_validate(data).subject == "person"
    data["subject"] = "pet"
    assert Pack.model_validate(data).subject == "pet"


def test_invalid_subject_rejected():
    data = _minimal_pack_dict()
    data["subject"] = "robot"
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_subject_desc_optional():
    data = _minimal_pack_dict()
    assert Pack.model_validate(data).subject_desc == ""
    data["subject_desc"] = "一只穿围裙的树懒玩偶"
    assert Pack.model_validate(data).subject_desc == "一只穿围裙的树懒玩偶"


def test_group_subject_accepted():
    data = _minimal_pack_dict()
    data["subject"] = "group"
    assert Pack.model_validate(data).subject == "group"


def test_pack_style_id_loads_and_defaults_empty():
    from pathlib import Path

    from mememe.core.schema import load_pack

    root = Path(__file__).parent.parent / "packs"
    assert load_pack(root / "yundong.yaml").style_id == "anime"
    assert load_pack(root / "shechu.yaml").style_id == ""  # 旗舰保持经典贴纸
