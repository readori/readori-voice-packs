"""Sample sentences used by ``smoke`` (one short line) and ``audit`` (one fixed paragraph)."""
from __future__ import annotations

from .common import first_language_subtag

SMOKE_TEXTS = {
    "zh": "今天天气很好，我们一起去公园散步吧。",
    "yue": "今日天氣好好，我哋一齊去公園散步啦。",
    "en": "The quick brown fox jumps over the lazy dog.",
    "ja": "今日はいい天気ですね。一緒に散歩に行きましょう。",
    "ko": "오늘은 날씨가 정말 좋네요. 같이 산책하러 가요.",
    "de": "Der schnelle braune Fuchs springt über den faulen Hund.",
    "fr": "Le renard brun rapide saute par-dessus le chien paresseux.",
    "es": "El rápido zorro marrón salta sobre el perro perezoso.",
    "ru": "Быстрая коричневая лиса прыгает через ленивую собаку.",
}

# The Chinese paragraph is the one used by readori-tts-voice-audit-v13.py, kept unchanged so
# measurements stay comparable with the catalogs that were audited before.
AUDIT_TEXTS = {
    "zh": "夜色渐深，风穿过树林。阅读让我们在文字中发现更大的世界。",
    "yue": "夜色漸深，風穿過樹林。閱讀令我哋喺文字入面發現更大嘅世界。",
    "en": "Night grew deep and the wind moved through the trees. Reading shows us a wider world in words.",
    "ja": "夜が更け、風が林を抜けていく。読書は言葉の中に、より広い世界を見せてくれる。",
    "ko": "밤이 깊어지고 바람이 숲을 지나간다. 독서는 글 속에서 더 넓은 세상을 보여 준다.",
}


def smoke_text(language: str | None, override: str | None = None) -> str:
    if override:
        return override
    return SMOKE_TEXTS.get(first_language_subtag(language), SMOKE_TEXTS["en"])


def audit_text(language: str | None, override: str | None = None) -> str:
    if override:
        return override
    sub = first_language_subtag(language)
    return AUDIT_TEXTS.get(sub) or SMOKE_TEXTS.get(sub, AUDIT_TEXTS["en"])
