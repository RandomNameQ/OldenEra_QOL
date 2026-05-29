from __future__ import annotations

import json
from pathlib import Path

from oldenera_qol.localization import DEFAULT_LOCALE, Translator, locale_for_wiki_language, normalize_locale


def test_normalize_locale_defaults_to_english_for_unknown_values() -> None:
    assert DEFAULT_LOCALE == "en"
    assert normalize_locale("EN_us") == "en"
    assert normalize_locale("zh_CN") == "zh-cn"
    assert normalize_locale("missing") == "en"


def test_locale_for_wiki_language_maps_source_folder_names() -> None:
    assert locale_for_wiki_language("English") == "en"
    assert locale_for_wiki_language("Russian") == "ru"
    assert locale_for_wiki_language("ChineseSimplified") == "zh-cn"
    assert locale_for_wiki_language("ChineseTraditional") == "zh-tw"


def test_translator_uses_selected_language_and_english_fallback(tmp_path: Path) -> None:
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en.json").write_text(
        json.dumps({"common": {"units": "Units", "welcome": "Hello {name}"}}),
        encoding="utf-8",
    )
    (locale_dir / "ru.json").write_text(
        json.dumps({"common": {"units": "Юниты"}}),
        encoding="utf-8",
    )

    translator = Translator(locale_dir, "ru")

    assert translator.t("common.units") == "Юниты"
    assert translator.t("common.welcome", name="Codex") == "Hello Codex"
    assert translator.t("common.missing") == "common.missing"

