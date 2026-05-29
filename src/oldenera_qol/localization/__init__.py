from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from string import Formatter
from typing import Any


DEFAULT_LOCALE = "en"


@dataclass(frozen=True, slots=True)
class Locale:
    code: str
    label: str
    wiki_language: str
    fallback: tuple[str, ...] = ("en",)


SUPPORTED_LOCALES: tuple[Locale, ...] = (
    Locale("en", "English", "English", ()),
    Locale("ru", "Русский", "Russian"),
    Locale("fr", "Français", "French"),
    Locale("de", "Deutsch", "German"),
    Locale("es", "Español", "Spanish"),
    Locale("cs", "Čeština", "Czech"),
    Locale("hu", "Magyar", "Hungarian"),
    Locale("ja", "日本語", "Japanese"),
    Locale("ko", "한국어", "Korean"),
    Locale("pl", "Polski", "Polish"),
    Locale("tr", "Türkçe", "Turkish"),
    Locale("uk", "Українська", "Ukrainian"),
    Locale("zh-cn", "简体中文", "ChineseSimplified"),
    Locale("zh-tw", "繁體中文", "ChineseTraditional"),
)

_LOCALE_BY_CODE = {locale.code: locale for locale in SUPPORTED_LOCALES}
_LOCALE_BY_WIKI_LANGUAGE = {
    locale.wiki_language.lower(): locale.code for locale in SUPPORTED_LOCALES
}
_LOCALE_ALIASES = {
    "zh": "zh-cn",
    "zhcn": "zh-cn",
    "zh-cn": "zh-cn",
    "zh_hans": "zh-cn",
    "zh-hans": "zh-cn",
    "zhtw": "zh-tw",
    "zh-tw": "zh-tw",
    "zh_hant": "zh-tw",
    "zh-hant": "zh-tw",
    "en-us": "en",
    "en-gb": "en",
    "ua": "uk",
}


def supported_locales() -> tuple[Locale, ...]:
    return SUPPORTED_LOCALES


def normalize_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    normalized = value.strip().lower().replace("_", "-")
    normalized = _LOCALE_ALIASES.get(normalized, normalized)
    if normalized in _LOCALE_BY_CODE:
        return normalized
    base = normalized.split("-", 1)[0]
    return base if base in _LOCALE_BY_CODE else DEFAULT_LOCALE


def locale_for_wiki_language(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    key = value.strip().lower()
    return _LOCALE_BY_WIKI_LANGUAGE.get(key, normalize_locale(value))


def wiki_language_for_locale(value: str) -> str:
    return _LOCALE_BY_CODE[normalize_locale(value)].wiki_language


class Translator:
    def __init__(self, locale_dir: Path, locale: str = DEFAULT_LOCALE) -> None:
        self.locale_dir = locale_dir
        self.locale = normalize_locale(locale)
        self._messages: dict[str, dict[str, Any]] = {}

    def set_locale(self, locale: str) -> None:
        self.locale = normalize_locale(locale)

    def t(self, key: str, **values: object) -> str:
        for locale in self._locale_chain():
            value = _read_nested(self._load_messages(locale), key)
            if isinstance(value, str):
                return _format_message(value, values)
        return key

    def _locale_chain(self) -> list[str]:
        locale = _LOCALE_BY_CODE.get(self.locale, _LOCALE_BY_CODE[DEFAULT_LOCALE])
        chain = [locale.code, *locale.fallback, DEFAULT_LOCALE]
        result: list[str] = []
        for code in chain:
            normalized = normalize_locale(code)
            if normalized not in result:
                result.append(normalized)
        return result

    def _load_messages(self, locale: str) -> dict[str, Any]:
        locale = normalize_locale(locale)
        cached = self._messages.get(locale)
        if cached is not None:
            return cached
        path = self.locale_dir / f"{locale}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self._messages[locale] = data
        return data


def _read_nested(tree: dict[str, Any], key: str) -> Any:
    node: Any = tree
    for part in key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _format_message(template: str, values: dict[str, object]) -> str:
    if not values:
        return template
    field_names = [
        field_name
        for _literal_text, field_name, _format_spec, _conversion in Formatter().parse(template)
        if field_name
    ]
    safe_values = {field_name: values.get(field_name, "{" + field_name + "}") for field_name in field_names}
    return template.format(**safe_values)
