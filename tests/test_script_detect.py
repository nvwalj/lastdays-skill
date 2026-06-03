from lib.script_detect import detect_script, is_foreign
from lib.schema import Item


def test_detect_basic_scripts():
    assert detect_script("US stock market") == "en"
    assert detect_script("国产大模型横评") == "zh"
    assert detect_script("人工知能のニュース") == "ja"      # kana present
    assert detect_script("인공지능 뉴스") == "ko"
    assert detect_script("Искусственный интеллект") == "ru"


def test_japanese_wins_over_han_when_kana_present():
    # Mixed kana + kanji is Japanese, not Chinese.
    assert detect_script("AIモデルの性能比較") == "ja"
    # Pure Han with no kana stays Chinese.
    assert detect_script("性能比较") == "zh"


def test_is_foreign():
    assert not is_foreign("Claude Code")        # en
    assert not is_foreign("大模型")              # zh
    assert is_foreign("生成AIの活用")            # ja
    assert is_foreign("생성형 AI")               # ko


def test_neutral_input_defaults_english():
    assert detect_script("") == "en"
    assert detect_script("123 !!! 🎉") == "en"   # digits/punct/emoji are neutral


def test_item_flags_foreign_title_in_dict():
    ja = Item(source="github", lang="en", title="AIモデルのバグ修正", url="u")
    en = Item(source="github", lang="en", title="Fix AI model bug", url="u2")
    assert ja.to_dict()["title_script"] == "ja"
    assert "title_script" not in en.to_dict()    # native titles add no noise
    assert ja.is_foreign() and not en.is_foreign()
