"""Unit coverage for the report-side i18n helpers."""
from app.match_report_i18n import (
    _TRANSLATIONS,
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
    t,
)


class TestKeyParity:
    """Every locale carries the full English key set.

    Runtime falls back to English for a missing key, so a gap never
    breaks the page — but it silently un-translates it. This pins the
    "add the key to all six locales" rule mechanically.
    """

    def test_all_locales_share_the_english_key_set(self):
        english = set(_TRANSLATIONS[DEFAULT_LOCALE])
        for locale in SUPPORTED_LOCALES:
            assert locale in _TRANSLATIONS
            missing = english - set(_TRANSLATIONS[locale])
            extra = set(_TRANSLATIONS[locale]) - english
            assert not missing, f"{locale} is missing keys: {sorted(missing)}"
            assert not extra, f"{locale} has extra keys: {sorted(extra)}"

    def test_placeholders_match_the_english_template(self):
        # A translated string must use exactly the English template's
        # placeholders — a stray or renamed field would raise at
        # ``str.format`` time and fall back to the raw template.
        import string
        formatter = string.Formatter()

        def _fields(template: str) -> set[str]:
            return {
                field for _, field, _, _ in formatter.parse(template) if field
            }

        for key, english_template in _TRANSLATIONS[DEFAULT_LOCALE].items():
            expected = _fields(english_template)
            for locale in SUPPORTED_LOCALES:
                assert _fields(_TRANSLATIONS[locale][key]) == expected, (
                    f"placeholder drift in {locale}:{key}"
                )


class TestResolveLocale:
    def test_none_falls_back_to_default(self):
        assert resolve_locale(None) == DEFAULT_LOCALE

    def test_empty_string_falls_back(self):
        assert resolve_locale("") == DEFAULT_LOCALE
        assert resolve_locale("   ") == DEFAULT_LOCALE

    def test_simple_supported_tag(self):
        assert resolve_locale("es") == "es"
        assert resolve_locale("de") == "de"

    def test_regional_subtag_is_stripped(self):
        # Browser sends ``es-ES`` / ``pt-BR``; the report only carries
        # the primary tag.
        assert resolve_locale("es-ES") == "es"
        assert resolve_locale("pt-BR") == "pt"

    def test_q_value_ranking(self):
        # Higher q wins. Spanish (q=0.9) beats English (q=0.8).
        assert resolve_locale("en;q=0.8,es;q=0.9") == "es"

    def test_declaration_order_breaks_ties(self):
        # Equal q (default 1.0) → first declared wins.
        assert resolve_locale("es,en") == "es"
        assert resolve_locale("en,es") == "en"

    def test_ignores_unknown_locales(self):
        # ``kl`` (Greenlandic) isn't supported; fall through to ``de``.
        assert resolve_locale("kl;q=1.0,de;q=0.5") == "de"

    def test_completely_unknown_falls_back(self):
        assert resolve_locale("kl,xx-YY") == DEFAULT_LOCALE

    def test_malformed_tags_are_skipped(self):
        # ``!!!`` fails the language-tag regex; English is still in the
        # list and wins.
        assert resolve_locale("!!!,en") == "en"

    def test_invalid_q_is_treated_as_zero(self):
        # ``q=potato`` parses to 0 → effectively excluded; ``de`` wins.
        assert resolve_locale("es;q=potato,de") == "de"

    def test_all_supported_locales_resolve_to_themselves(self):
        for locale in SUPPORTED_LOCALES:
            assert resolve_locale(locale) == locale


class TestTranslate:
    def test_known_key_in_default_locale(self):
        assert t("en", "matchFacts") == "Match facts"

    def test_known_key_in_other_locale(self):
        assert t("es", "matchFacts") == "Datos del partido"

    def test_missing_key_falls_back_to_key_string(self):
        assert t("en", "this.key.does.not.exist") == "this.key.does.not.exist"

    def test_format_arguments_are_interpolated(self):
        assert t("en", "actionPoint", team=2) == "Point — Team 2"
        assert t("es", "actionPoint", team=1) == "Punto — Equipo 1"

    def test_missing_format_arg_returns_template(self):
        # Missing ``team`` → format raises KeyError → return raw template
        # so the page never 500s on a translation typo.
        result = t("en", "actionPoint")
        assert "Team" in result and "{team}" in result

    def test_unknown_locale_falls_back_to_english(self):
        # ``zz`` isn't in the dict; English string wins.
        assert t("zz", "matchFacts") == "Match facts"
