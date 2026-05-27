"""
Site identity configuration for the translate.py engine.

This file is per-project. The translate.py engine in this directory should
be byte-identical to the engine in any sister project (zero-parades, etc.);
only this config diverges.

When syncing engine improvements between projects, use:

    cp ../<sister-project>/scripts/translate.py scripts/translate.py

This config file (translate_config.py) stays put. The invariant to defend
is: a diff of two projects' translate.py should approach zero over time.
"""
from __future__ import annotations

from decimal import Decimal

# === Site identity ===
SITE_URL = "https://paralivesguide.help"
BRAND_NAME = "Paralives Guide"
GAME_NAME = "Paralives"
GAME_STUDIO = "Paralives Studio"
GAME_GENRE_DESCRIPTION = "cozy life-sim"

# === Languages ===
# (code, native_name). First entry must be the source language. Order
# determines the language switcher widget order on every page.
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("de", "Deutsch"),
    ("pl", "Polski"),
    ("pt-BR", "Português (Brasil)"),
    ("es-419", "Español (América Latina)"),
    ("zh-CN", "简体中文"),
]

# === LLM models ===
DEFAULT_MODEL = "gpt-5.4"
FALLBACK_MODEL = "gpt-5.2"
MODEL_PRICING = {
    "gpt-5.4": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5.3": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5.2": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5": {"input": Decimal("1.25"), "output": Decimal("10.00")},
    "gpt-5.1": {"input": Decimal("1.25"), "output": Decimal("10.00")},
}

# === AdSense ===
# Empty string disables AdSense restore + validate (used when the site is
# pre-grant and the source pages have <script> tags commented out). When
# the project is granted an AdSense client id, set this to the live src URL,
# e.g. "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX".
ADSENSE_SRC = ""

# === Contact / About link ===
# Filename on the site that hosts contact information. Footer translation
# notice links here. paralives folds contact into about.html; other sites
# may use contact.html.
ABOUT_PAGE_FILENAME = "about.html"
ABOUT_LINK_TEXT = "About page"

# === Footer translation notice ===
# Use {about_link} as the placeholder for the linked About-page text. The
# engine partitions the template around this placeholder and inserts an
# <a> element using ABOUT_PAGE_FILENAME and ABOUT_LINK_TEXT.
TRANSLATION_NOTICE_TEMPLATE = (
    "Machine-assisted translation from English. Report errors via the {about_link}."
)

# === Translation prompt content ===
# Proper nouns the LLM must preserve verbatim. The HTML-level translate="no"
# attribute is the authoritative contract for arbitrary spans; this list is
# the smaller belt-and-braces set the system prompt names explicitly.
PROPER_NOUNS_TO_PRESERVE = [
    "Paralives Guide",
    "Paralives",
    "Paralives Studio",
    "Paramaker",
    "Para",
    "Paras",
    "The Sims",
    "EA",
    "Electronic Arts",
]

# Category code prefixes used by the site's glyph code system. The LLM must
# not translate or alter any token matching r"<prefix>-\d+", e.g. "GD-01".
GLYPH_CODE_PREFIXES = ["GD", "DB", "TL", "HS"]

# Site-specific rules appended to the prompt's "Rules" list. Each entry is
# rendered as one numbered bullet. Keep concise; the engine numbers them
# automatically.
EXTRA_RULES = [
    'Build version strings: "EA 0.4", "Early Access", and any "build X.Y" token are preserved verbatim.',
    'Title pattern: every <title> ends with " | Paralives Guide" — keep that wordmark suffix verbatim, even though it follows the translated title.',
]

# One-sentence tone directive for the system prompt. Sets register; the
# engine inserts this verbatim.
TONE_DIRECTIVE = (
    "Tone: warm, opinionated, build-aware. Read like a thoughtful friend "
    "explaining the game, not like a marketing brochure and not like a "
    "literal dictionary swap. Do not add hype words, exclamation chains, "
    "or emoji clusters."
)

# === Language switcher CSS ===
# Injected into every translated page's <style> block by inject_style_rules.
# Uses CSS variables that must exist in the site's :root.
LANG_SWITCH_CSS = """
  .lang-switch {
    appearance: none;
    background: var(--cream);
    border: 1px solid var(--line);
    color: var(--ink);
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.05em;
    padding: 8px 30px 8px 10px;
    border-radius: 6px;
  }
  .lang-switch:focus {
    outline: none;
    border-color: var(--pink-deep);
    box-shadow: 0 0 0 1px var(--pink-deep);
  }
  .translation-notice {
    margin-top: 18px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--ink-soft);
  }
  @media (max-width: 540px) {
    .lang-switch {
      padding: 7px 26px 7px 8px;
      font-size: 11px;
      max-width: 160px;
    }
  }
""".strip("\n")
