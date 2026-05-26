#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, OpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://zeroparadesguide.wiki"
DEFAULT_MODEL = "gpt-5.4"
FALLBACK_MODEL = "gpt-5.2"
ADSENSE_SRC = (
    "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"
    "?client=ca-pub-4624485020338199"
)
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("fr", "Français"),
    ("es", "Español"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("id", "Bahasa Indonesia"),
    ("pl", "Polski"),
]
LANGUAGE_MAP = dict(LANGUAGES)
NON_ENGLISH = [code for code, _ in LANGUAGES if code != "en"]
MODEL_PRICING = {
    "gpt-5.4": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5.3": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5.2": {"input": Decimal("1.75"), "output": Decimal("14.00")},
    "gpt-5": {"input": Decimal("1.25"), "output": Decimal("10.00")},
    "gpt-5.1": {"input": Decimal("1.25"), "output": Decimal("10.00")},
}
RETRY_BACKOFF_SECONDS = [2, 4, 8, 16, 32]
TRANSLATION_NOTICE = (
    "Machine-assisted translation from English. Report errors via the Contact page."
)
LANG_SWITCH_CSS = """
  .lang-switch{
    appearance:none;
    background:var(--surface);
    border:1px solid var(--line);
    color:var(--ink);
    font-family:'Courier Prime',monospace;
    font-size:12px;
    letter-spacing:1px;
    text-transform:uppercase;
    padding:8px 30px 8px 10px;
    border-radius:0;
  }
  .lang-switch:focus{
    outline:none;
    border-color:var(--amber);
    box-shadow:0 0 0 1px var(--amber);
  }
  .translation-notice{
    margin-top:26px;
    font-family:'Courier Prime',monospace;
    font-size:11px;
    line-height:1.7;
    color:var(--ink-dim);
  }
  @media(max-width:540px){
    .lang-switch{
      padding:7px 26px 7px 8px;
      font-size:11px;
      max-width:160px;
    }
  }
""".strip("\n")
DOCTYPE_RE = re.compile(r"^\s*(?:<!DOCTYPE html>\s*)+", re.IGNORECASE)


@dataclass
class TranslationResult:
    source_file: str
    target_lang: str
    status: str
    output_path: str | None = None
    failure: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    model: str = DEFAULT_MODEL
    accepted_model: str | None = None
    model_substitution: str | None = None


@dataclass
class ScopeSelection:
    languages: list[str] | None = None
    files: list[Path] | None = None


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    accepted_models: list[str] | None = None
    model_substitution: str | None = None


@dataclass
class TranslationUnit:
    unit_id: str
    kind: str
    payload: str
    node: Any = None
    extra: Any = None


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_files() -> list[Path]:
    return sorted(REPO_ROOT.glob("*.html"))


def source_commit_for(path: Path) -> str:
    return run_git(["log", "-n", "1", "--format=%H", "--", path.name])


def url_for(lang: str, filename: str) -> str:
    if lang == "en":
        return f"{SITE_URL}/{filename}"
    return f"{SITE_URL}/{lang}/{filename}"


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env")


def require_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to the repo-local .env file or "
            "your shell environment. Create a key at https://platform.openai.com/api-keys"
    )
    return api_key


def configured_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"


def strip_trailing_v1(base_url: str) -> str:
    return re.sub(r"/v1/?$", "", base_url.rstrip("/"))


def fetch_models_once(base_url: str, api_key: str) -> tuple[int, str, object]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    parsed = None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    return status, body, parsed


def preflight_models(api_key: str) -> tuple[str, list[str], bool]:
    attempted_base_url = configured_base_url()
    attempts = [attempted_base_url]

    stripped = strip_trailing_v1(attempted_base_url)
    if stripped and stripped != attempted_base_url.rstrip("/"):
        attempts.append(stripped)

    last_status = None
    last_body = None
    for index, base_url in enumerate(attempts):
        status, body, parsed = fetch_models_once(base_url, api_key)
        last_status = status
        last_body = body
        is_valid_json = isinstance(parsed, dict)
        if status == 200 and is_valid_json:
            data = parsed.get("data")
            if not isinstance(data, list):
                raise SystemExit(f"{base_url}/models returned 200 JSON but no data list.")
            model_ids = [item.get("id") for item in data if isinstance(item, dict) and item.get("id")]
            print(f"Successful /models base_url: {base_url}")
            print("Model IDs:")
            for model_id in model_ids:
                print(model_id)
            print(f"Standard Bearer auth verified: {'yes' if status == 200 and is_valid_json else 'no'}")
            return base_url, model_ids, True

        should_retry = index == 0 and (status == 404 or parsed is None) and len(attempts) > 1
        if should_retry:
            print(
                f"Initial /models probe failed for {base_url} with status={status} "
                f"and json={'yes' if parsed is not None else 'no'}. Retrying without trailing /v1."
            )
            continue

        raise SystemExit(
            f"/models preflight failed for {base_url}: status={status}, "
            f"json={'yes' if parsed is not None else 'no'}, body={body[:500]}"
        )

    raise SystemExit(
        f"/models preflight failed after retries: status={last_status}, body={(last_body or '')[:500]}"
    )


def pricing_for_model(model: str) -> dict[str, Decimal] | None:
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    base = model.split("-20")[0]
    return MODEL_PRICING.get(base)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = pricing_for_model(model)
    if pricing is None:
        return Decimal("0")
    input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing["input"]
    output_cost = (Decimal(output_tokens) / Decimal("1000000")) * pricing["output"]
    return (input_cost + output_cost).quantize(Decimal("0.000001"))


def usage_from_response(response) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0, 0
    input_tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens)
    return int(input_tokens), int(output_tokens), int(total_tokens)


def build_alternate_links(filename: str) -> list[tuple[str, str]]:
    links = [(code, url_for(code, filename)) for code, _ in LANGUAGES]
    links.append(("x-default", url_for("en", filename)))
    return links


def ensure_head_metadata(soup: BeautifulSoup, lang: str, filename: str, source_commit: str) -> None:
    html_tag = soup.html
    if html_tag is None:
        raise ValueError("Missing <html> element")
    html_tag["lang"] = lang

    head = soup.head
    if head is None:
        raise ValueError("Missing <head> element")

    canonical_href = url_for(lang, filename)
    canonical = head.find("link", attrs={"rel": "canonical"})
    if canonical is None:
        canonical = soup.new_tag("link", rel="canonical")
        head.append(canonical)
    canonical["href"] = canonical_href

    for existing in head.find_all("link", attrs={"rel": "alternate"}):
        existing.decompose()
    for hreflang, href in build_alternate_links(filename):
        tag = soup.new_tag("link", rel="alternate", hreflang=hreflang, href=href)
        head.append(tag)

    upsert_meta(head, soup, "translation-source-commit", source_commit)
    upsert_meta(head, soup, "translation-source-path", filename)


def upsert_meta(head: BeautifulSoup, soup: BeautifulSoup, name: str, content: str) -> None:
    tag = head.find("meta", attrs={"name": name})
    if tag is None:
        tag = soup.new_tag("meta")
        tag["name"] = name
        head.append(tag)
    tag["content"] = content


def inject_lang_switch(soup: BeautifulSoup, lang: str, filename: str) -> None:
    nav = soup.select_one("header.topbar nav.main")
    if nav is None:
        raise ValueError("Missing top navigation")

    existing = nav.select_one("select.lang-switch")
    if existing is not None:
        existing.decompose()

    select = soup.new_tag(
        "select",
        attrs={
            "class": "lang-switch",
            "onchange": "if(this.value)location.href=this.value",
        },
    )
    placeholder = soup.new_tag("option", value="")
    placeholder["selected"] = ""
    placeholder["disabled"] = ""
    placeholder.string = f"{lang.upper()} · {LANGUAGE_MAP[lang]}"
    select.append(placeholder)

    for code, native_name in LANGUAGES:
        option = soup.new_tag("option", value=url_for(code, filename))
        option.string = f"{code.upper()} · {native_name}"
        select.append(option)

    about_link = nav.find("a", class_="nav-about")
    if about_link is not None:
        about_link.insert_after(select)
    else:
        nav.append(select)


def ensure_en_head_metadata(soup: BeautifulSoup, filename: str) -> None:
    html_tag = soup.html
    if html_tag is None:
        raise ValueError("Missing <html> element")
    html_tag["lang"] = "en"

    head = soup.head
    if head is None:
        raise ValueError("Missing <head> element")

    canonical_href = url_for("en", filename)
    canonical = head.find("link", attrs={"rel": "canonical"})
    if canonical is None:
        canonical = soup.new_tag("link", rel="canonical")
        head.append(canonical)
    canonical["href"] = canonical_href

    for existing in head.find_all("link", attrs={"rel": "alternate"}):
        existing.decompose()
    for hreflang, href in build_alternate_links(filename):
        tag = soup.new_tag("link", rel="alternate", hreflang=hreflang, href=href)
        head.append(tag)


def inject_style_rules(soup: BeautifulSoup, source_soup: BeautifulSoup) -> None:
    style = soup.find("style")
    source_style = source_soup.find("style")
    if source_style is None:
        return
    if style is None:
        soup.head.append(source_style)
        style = soup.find("style")
    else:
        style.string = source_style.string
    if style.string and ".lang-switch" not in style.string:
        style.string = f"{style.string.rstrip()}\n{LANG_SWITCH_CSS}\n"


def restore_adsense_script(soup: BeautifulSoup, source_soup: BeautifulSoup) -> None:
    for tag in soup.find_all("script", src=True):
        if "adsbygoogle.js" in tag.get("src", ""):
            tag.decompose()
    source_tag = source_soup.find("script", src=re.compile(r"adsbygoogle\.js"))
    if source_tag is None:
        raise ValueError("Missing AdSense script in source page")
    soup.head.append(source_tag)


def inject_translation_notice(soup: BeautifulSoup, lang: str) -> None:
    disclaimer = soup.select_one("footer .disclaimer")
    if disclaimer is None:
        raise ValueError("Missing footer disclaimer")
    existing = soup.select_one("footer .translation-notice")
    if existing is not None:
        existing.decompose()

    paragraph = soup.new_tag("p", attrs={"class": "translation-notice"})
    em = soup.new_tag("em")
    em.append(TRANSLATION_NOTICE.split("Contact page")[0])
    contact_link = soup.new_tag("a", href=url_for(lang, "contact.html"))
    contact_link.string = "Contact page"
    em.append(contact_link)
    em.append(".")
    paragraph.append(em)
    disclaimer.insert_before(paragraph)


def validate_output(soup: BeautifulSoup, lang: str, filename: str, source_commit: str) -> None:
    if soup.html is None or soup.html.get("lang") != lang:
        raise ValueError("Translated page is missing the correct html lang attribute")
    meta_commit = soup.find("meta", attrs={"name": "translation-source-commit"})
    if meta_commit is None or meta_commit.get("content") != source_commit:
        raise ValueError("Translated page is missing the correct translation-source-commit meta")
    meta_path = soup.find("meta", attrs={"name": "translation-source-path"})
    if meta_path is None or meta_path.get("content") != filename:
        raise ValueError("Translated page is missing the correct translation-source-path meta")
    adsense = soup.find("script", src=ADSENSE_SRC)
    if adsense is None:
        raise ValueError("AdSense script was not preserved verbatim")


def build_prompt(lang: str, filename: str, source_commit: str, source_html: str) -> tuple[str, str]:
    native_name = LANGUAGE_MAP[lang]
    system = (
        "You are translating a single HTML page of a noir-styled fan wiki about "
        f"the video game ZERO PARADES: For Dead Spies, from English to {native_name}. "
        "The page is for ad-supported public deployment, so translation must be natural, "
        "idiomatic, and grammatically clean, not literal.\n\n"
        "Rules:\n"
        "1. Translate visible prose, headings, labels, and meta description.\n"
        "2. Preserve verbatim (do NOT translate):\n"
        '   - Brand "Portofiro//Dossier"\n'
        "   - Proper nouns: ZERO PARADES, ZERO PARADES: For Dead Spies, Disco Elysium, "
        "ZA/UM, Portofiro, Revachol, Hershel Wilk, CASCADE, real-person names, and studio names.\n"
        "   - URLs, file paths, CSS class names, IDs, data-attributes.\n"
        "   - <script> blocks, <style> blocks, the AdSense identifier, glyph codes like GD-01, DB-01, TL-01,\n"
        '     case-file stamps like "CASE FILE ZP-001", and date strings in YYYY-MM-DD format.\n'
        '   - The "| Portofiro Dossier" suffix in <title>.\n'
        '   - The editorial markers "<b>NOTE:</b>" and "<b>FILL IN:</b>".\n'
        f"3. Set <html lang> to {lang}, canonical to {url_for(lang, filename)}, "
        f"translation-source-commit to {source_commit}, and translation-source-path to {filename}.\n"
        "4. Keep the dossier voice: terse, source-tight, no marketing language, no exclamation marks, no emoji.\n"
        "5. Return ONLY the complete translated HTML document, starting with <!DOCTYPE html>.\n"
    )
    user = f"Translate this HTML document to {native_name}:\n\n{source_html}"
    return system, user


def build_chunk_prompt(lang: str, filename: str, units: list[TranslationUnit]) -> tuple[str, str]:
    native_name = LANGUAGE_MAP[lang]
    system = (
        "You are translating extracted content fragments from a single HTML page of a noir-styled "
        f"fan wiki about ZERO PARADES: For Dead Spies, from English to {native_name}. "
        "Translate naturally and idiomatically, while preserving source-tight tone.\n\n"
        "Return valid JSON only: an object with key \"translations\" whose value is an array of "
        "{\"id\": string, \"text\": string} objects.\n\n"
        "Rules:\n"
        '1. Preserve verbatim: "Portofiro//Dossier", ZERO PARADES, ZERO PARADES: For Dead Spies, '
        "Disco Elysium, ZA/UM, Portofiro, Revachol, Hershel Wilk, CASCADE, studio names, real-person names.\n"
        "2. Preserve URLs, file paths, CSS class names, IDs, data-attributes, glyph codes like GD-01/DB-01/TL-01, "
        "case-file stamps like CASE FILE ZP-001, and date strings.\n"
        "3. Preserve HTML inline tags already inside a fragment, such as <strong>, <em>, <b>, <a>, and entities.\n"
        '4. Preserve the "<b>NOTE:</b>" and "<b>FILL IN:</b>" markers in English.\n'
        "5. Do not add commentary, markdown, or explanations.\n"
    )
    payload = {
        "filename": filename,
        "target_language": native_name,
        "units": [{"id": unit.unit_id, "kind": unit.kind, "text": unit.payload} for unit in units],
    }
    return system, json.dumps(payload, ensure_ascii=False)


def chat_completion(client: OpenAI, model: str, system: str, user: str):
    max_attempts = len(RETRY_BACKOFF_SECONDS) + 1
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(
                model=model,
                temperature=0,
                timeout=120,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except BadRequestError:
            raise
        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code is not None and 400 <= int(status_code) < 500:
                raise
            if attempt == max_attempts:
                raise
            print(
                f"Retry {attempt}/{len(RETRY_BACKOFF_SECONDS)} after API {status_code} for chat completion: {exc}",
                flush=True,
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
        except (APIConnectionError, APITimeoutError) as exc:
            if attempt == max_attempts:
                raise
            print(
                f"Retry {attempt}/{len(RETRY_BACKOFF_SECONDS)} after {type(exc).__name__} for chat completion: {exc}",
                flush=True,
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])


def accepted_model_id(response: Any, fallback: str) -> str:
    if hasattr(response, "model") and response.model:
        return str(response.model)
    return fallback


def is_invalid_model_error(message: str) -> bool:
    lowered = message.lower()
    return "invalid model" in lowered or "model_not_found" in lowered or "does not exist" in lowered


def parse_json_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


def serialize_document(soup: BeautifulSoup) -> str:
    rendered = str(soup)
    body = DOCTYPE_RE.sub("", rendered, count=1).lstrip()
    return f"<!DOCTYPE html>\n{body}"


def parse_only_scope(value: str) -> ScopeSelection:
    tokens = [item.strip() for item in value.split(",") if item.strip()]
    if not tokens:
        raise argparse.ArgumentTypeError("--only requires at least one comma-separated value")

    available_files = {path.name: path for path in source_files()}
    available_langs = set(NON_ENGLISH)
    token_set = set(tokens)

    if token_set.issubset(available_langs):
        selected_langs: list[str] = []
        seen_langs: set[str] = set()
        for code in tokens:
            if code in seen_langs:
                continue
            seen_langs.add(code)
            selected_langs.append(code)
        return ScopeSelection(languages=selected_langs)

    if token_set.issubset(set(available_files)):
        selected_files: list[Path] = []
        seen_files: set[str] = set()
        for name in tokens:
            if name in seen_files:
                continue
            seen_files.add(name)
            selected_files.append(available_files[name])
        return ScopeSelection(files=selected_files)

    unknown = [token for token in tokens if token not in available_langs and token not in available_files]
    if unknown:
        raise argparse.ArgumentTypeError(f"Unknown --only value(s): {', '.join(unknown)}")
    raise argparse.ArgumentTypeError("--only must be either all language codes or all source filenames")


def select_unique(nodes: list[Any]) -> list[Any]:
    seen: set[int] = set()
    unique: list[Any] = []
    for node in nodes:
        marker = id(node)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(node)
    return unique


def text_like_nodes(soup: BeautifulSoup) -> list[Any]:
    selectors = [
        "title",
        'meta[name="description"]',
        ".kicker",
        "h1",
        ".byline",
        ".meta",
        ".toc h2",
        ".toc a",
        ".crumb",
        "article h2.sec",
        "article h3",
        "article h4",
        "main h2",
        "main h3",
        "main h4",
        "p",
        "li",
        ".note",
        ".ad-slot",
        ".faq summary",
        ".faq details p",
        ".related-grid .t",
        ".related-grid .h",
        ".factbox h3",
        ".factbox td",
        ".route-status",
        ".section-link",
        ".dispatch .body h4",
        ".dispatch .body p",
        ".mailbox .label",
        "footer h5",
        "footer p",
        "footer a",
        ".sec-head h2",
        ".sec-head .no",
        ".scale-strip",
        ".card .tag",
        ".card h3",
        ".card p",
        ".card .go",
    ]
    found: list[Any] = []
    for selector in selectors:
        found.extend(soup.select(selector))
    return select_unique(found)


def should_translate_node(node: Any) -> bool:
    if getattr(node, "name", None) == "meta":
        return bool(node.get("content", "").strip())
    text = node.decode_contents().strip()
    if not text:
        return False
    if node.name == "p" and "disclaimer" in (node.get("class") or []):
        return True
    if node.name == "script":
        return False
    return True


def collect_translation_units(soup: BeautifulSoup, lang: str) -> list[TranslationUnit]:
    units: list[TranslationUnit] = []
    for node in text_like_nodes(soup):
        if not should_translate_node(node):
            continue
        unit_id = str(uuid.uuid4())
        if node.name == "meta":
            payload = node.get("content", "")
            kind = "text"
        elif node.name == "title":
            payload = node.get_text()
            kind = "text"
        else:
            payload = node.decode_contents()
            kind = "html"
        units.append(TranslationUnit(unit_id=unit_id, kind=kind, payload=payload, node=node))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "FAQPage":
            continue
        main_entities = data.get("mainEntity", [])
        for index, entity in enumerate(main_entities):
            if isinstance(entity, dict) and entity.get("name"):
                units.append(
                    TranslationUnit(
                        unit_id=str(uuid.uuid4()),
                        kind="json_text",
                        payload=entity["name"],
                        node=script,
                        extra=("faq_name", index),
                    )
                )
            answer = entity.get("acceptedAnswer") if isinstance(entity, dict) else None
            if isinstance(answer, dict) and answer.get("text"):
                units.append(
                    TranslationUnit(
                        unit_id=str(uuid.uuid4()),
                        kind="json_text",
                        payload=answer["text"],
                        node=script,
                        extra=("faq_text", index),
                    )
                )

    if lang != "en":
        units.append(
            TranslationUnit(
                unit_id=str(uuid.uuid4()),
                kind="html",
                payload='Machine-assisted translation from English. Report errors via the <a href="contact.html">Contact page</a>.',
                node=None,
                extra="translation_notice",
            )
        )
    return units


def batched_units(units: list[TranslationUnit], max_units: int = 12, max_chars: int = 3200) -> list[list[TranslationUnit]]:
    batches: list[list[TranslationUnit]] = []
    batch: list[TranslationUnit] = []
    size = 0
    for unit in units:
        unit_size = len(unit.payload)
        if batch and (len(batch) >= max_units or size + unit_size > max_chars):
            batches.append(batch)
            batch = []
            size = 0
        batch.append(unit)
        size += unit_size
    if batch:
        batches.append(batch)
    return batches


def request_chunk_translation(
    client: OpenAI,
    model: str,
    lang: str,
    filename: str,
    units: list[TranslationUnit],
    fallback_model: str | None,
) -> tuple[dict[str, str], UsageTotals, str]:
    system, user = build_chunk_prompt(lang, filename, units)
    substitution_note = None
    try:
        response = chat_completion(client, model, system, user)
    except BadRequestError as exc:
        message = str(exc)
        if fallback_model and fallback_model != model and is_invalid_model_error(message):
            response = chat_completion(client, fallback_model, system, user)
            substitution_note = f"{model} -> {fallback_model}"
            model = fallback_model
        else:
            raise RuntimeError(message) from exc
    text = response.choices[0].message.content or ""
    payload = parse_json_response(text)
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise RuntimeError("Model response did not include a translations array")
    mapping: dict[str, str] = {}
    for item in translations:
        if isinstance(item, dict) and item.get("id") and isinstance(item.get("text"), str):
            mapping[item["id"]] = item["text"]
    input_tokens, output_tokens, total_tokens = usage_from_response(response)
    accepted = accepted_model_id(response, model)
    usage = UsageTotals(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=compute_cost(model, input_tokens, output_tokens),
        accepted_models=[accepted],
        model_substitution=substitution_note,
    )
    return mapping, usage, model


def apply_translation_units(soup: BeautifulSoup, units: list[TranslationUnit], translated: dict[str, str], lang: str) -> str:
    json_updates: dict[int, dict[tuple[str, int], str]] = {}
    notice_html = None
    for unit in units:
        text = translated.get(unit.unit_id)
        if text is None:
            raise RuntimeError(f"Missing translated chunk for {unit.unit_id}")
        if unit.extra == "translation_notice":
            notice_html = text
            continue
        if unit.kind == "json_text":
            key = id(unit.node)
            bucket = json_updates.setdefault(key, {})
            bucket[unit.extra] = text
            continue
        if unit.node.name == "meta":
            unit.node["content"] = text
        elif unit.node.name == "title":
            unit.node.string = text
        else:
            fragment = BeautifulSoup(text, "html.parser")
            unit.node.clear()
            for child in list(fragment.contents):
                unit.node.append(child)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        updates = json_updates.get(id(script))
        if not updates:
            continue
        data = json.loads(script.string or "")
        for (kind, index), value in updates.items():
            entity = data["mainEntity"][index]
            if kind == "faq_name":
                entity["name"] = value
            elif kind == "faq_text":
                entity["acceptedAnswer"]["text"] = value
        script.string = json.dumps(data, ensure_ascii=False, indent=2)

    if notice_html is not None:
        disclaimer = soup.select_one("footer .disclaimer")
        if disclaimer is None:
            raise RuntimeError("Missing footer disclaimer")
        existing = soup.select_one("footer .translation-notice")
        if existing is not None:
            existing.decompose()
        paragraph = soup.new_tag("p", attrs={"class": "translation-notice"})
        em = soup.new_tag("em")
        fragment = BeautifulSoup(notice_html, "html.parser")
        for child in list(fragment.contents):
            em.append(child)
        for anchor in em.find_all("a"):
            anchor["href"] = url_for(lang, "contact.html")
        paragraph.append(em)
        disclaimer.insert_before(paragraph)
    return notice_html or ""


def translate_page_in_chunks(
    client: OpenAI,
    source_path: Path,
    lang: str,
    model: str,
    fallback_model: str | None,
) -> tuple[BeautifulSoup, UsageTotals, str]:
    source_html = source_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(source_html, "html.parser")
    units = collect_translation_units(soup, lang)
    usage = UsageTotals(accepted_models=[])
    translated: dict[str, str] = {}
    active_model = model
    for batch in batched_units(units):
        mapping, batch_usage, active_model = request_chunk_translation(
            client, active_model, lang, source_path.name, batch, fallback_model
        )
        translated.update(mapping)
        usage.input_tokens += batch_usage.input_tokens
        usage.output_tokens += batch_usage.output_tokens
        usage.total_tokens += batch_usage.total_tokens
        usage.cost_usd += batch_usage.cost_usd
        usage.accepted_models.extend(batch_usage.accepted_models or [])
        if batch_usage.model_substitution:
            usage.model_substitution = batch_usage.model_substitution
    apply_translation_units(soup, units, translated, lang)
    return soup, usage, active_model


def translate_one(
    client: OpenAI,
    source_path: Path,
    lang: str,
    model: str,
    force: bool,
    fallback_model: str | None = None,
) -> TranslationResult:
    source_commit = source_commit_for(source_path)
    target_dir = REPO_ROOT / lang
    target_path = target_dir / source_path.name

    if target_path.exists() and not force:
        soup = BeautifulSoup(target_path.read_text(encoding="utf-8"), "html.parser")
        meta = soup.find("meta", attrs={"name": "translation-source-commit"})
        if meta and meta.get("content") == source_commit:
            return TranslationResult(
                source_file=source_path.name,
                target_lang=lang,
                status="skipped",
                output_path=str(target_path.relative_to(REPO_ROOT)),
                model=model,
            )

    try:
        soup, usage, model = translate_page_in_chunks(client, source_path, lang, model, fallback_model)
    except Exception as exc:  # noqa: BLE001
        return TranslationResult(
            source_file=source_path.name,
            target_lang=lang,
            status="failed",
            failure=f"{type(exc).__name__}: {exc}",
            model=model,
        )

    try:
        source_html = source_path.read_text(encoding="utf-8")
        source_soup = BeautifulSoup(source_html, "html.parser")
        ensure_head_metadata(soup, lang, source_path.name, source_commit)
        inject_lang_switch(soup, lang, source_path.name)
        inject_style_rules(soup, source_soup)
        restore_adsense_script(soup, source_soup)
        validate_output(soup, lang, source_path.name, source_commit)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(serialize_document(soup), encoding="utf-8")
        return TranslationResult(
            source_file=source_path.name,
            target_lang=lang,
            status="translated",
            output_path=str(target_path.relative_to(REPO_ROOT)),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd.quantize(Decimal("0.000001")),
            model=model,
            accepted_model=(usage.accepted_models or [model])[-1],
            model_substitution=usage.model_substitution,
        )
    except Exception as exc:  # noqa: BLE001
        return TranslationResult(
            source_file=source_path.name,
            target_lang=lang,
            status="failed",
            failure=f"{type(exc).__name__}: {exc}",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd.quantize(Decimal("0.000001")),
            model=model,
            accepted_model=(usage.accepted_models or [model])[-1],
            model_substitution=usage.model_substitution,
        )


def run_inject_en_metadata(_: argparse.Namespace) -> int:
    injected = 0
    skipped = 0
    for source in source_files():
        soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
        already_injected = (
            soup.head is not None
            and soup.head.find("link", attrs={"rel": "alternate", "hreflang": "de"}) is not None
            and soup.select_one("select.lang-switch") is not None
        )
        if already_injected:
            skipped += 1
            continue

        ensure_en_head_metadata(soup, source.name)
        inject_lang_switch(soup, "en", source.name)
        source.write_text(serialize_document(soup), encoding="utf-8")
        injected += 1

    print(f"injected: {injected} files; skipped (already done): {skipped} files", flush=True)
    return 0


def write_sitemap() -> None:
    items = []
    for source in source_files():
        links = "\n".join(
            f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{href}"/>'
            for hreflang, href in build_alternate_links(source.name)
        )
        items.append(
            "  <url>\n"
            f"    <loc>{url_for('en', source.name)}</loc>\n"
            f"{links}\n"
            "  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(items)
        + "\n</urlset>\n"
    )
    (REPO_ROOT / "sitemap.xml").write_text(xml, encoding="utf-8")


def should_regenerate_sitemap(targets: list[str], files: list[Path]) -> bool:
    if len(files) != len(source_files()):
        return False
    if set(targets) == set(NON_ENGLISH):
        return True
    return all((REPO_ROOT / lang).exists() for lang in NON_ENGLISH)


def run_translate(args: argparse.Namespace) -> int:
    load_env()
    api_key = require_api_key()
    base_url, _, _ = preflight_models(api_key)
    model = os.environ.get("TRANSLATE_MODEL", DEFAULT_MODEL)
    fallback_model = os.environ.get("TRANSLATE_MODEL_FALLBACK", FALLBACK_MODEL)
    client = OpenAI(api_key=api_key, base_url=base_url)

    targets = [args.lang] if args.lang else NON_ENGLISH
    if args.only and args.only.languages is not None:
        if args.lang:
            raise SystemExit("Use either --lang or --only with language codes, not both.")
        targets = args.only.languages
        files = source_files()
    elif args.only and args.only.files is not None:
        files = args.only.files
    elif args.file:
        files = [REPO_ROOT / args.file]
    else:
        files = source_files()

    results: list[TranslationResult] = []
    substitution_notes: list[str] = []
    for lang in targets:
        for source in files:
            result = translate_one(client, source, lang, model, args.force, fallback_model=fallback_model)
            results.append(result)
            if result.model_substitution:
                substitution_notes.append(result.model_substitution)
                model = result.model
            accepted_model_text = f" [accepted_model={result.accepted_model}]" if result.accepted_model else ""
            status_line = f"[{lang}] {source.name}: {result.status}{accepted_model_text}"
            if result.output_path:
                status_line += f" -> {result.output_path}"
            if result.failure:
                status_line += f" ({result.failure})"
            print(status_line, flush=True)

    if should_regenerate_sitemap(targets, files):
        write_sitemap()
        print("Regenerated sitemap.xml")
    else:
        print("Skipped sitemap.xml regeneration for this scoped test run.", flush=True)

    summary: dict[str, dict[str, int]] = {}
    total_cost = Decimal("0")
    total_input = 0
    total_output = 0
    total_tokens = 0
    accepted_models: list[str] = []
    for result in results:
        bucket = summary.setdefault(result.target_lang, {"translated": 0, "skipped": 0, "failed": 0})
        bucket[result.status] += 1
        total_cost += result.cost_usd
        total_input += result.input_tokens
        total_output += result.output_tokens
        total_tokens += result.total_tokens
        if result.accepted_model:
            accepted_models.append(result.accepted_model)

    print("\nSummary:", flush=True)
    for lang in targets:
        bucket = summary.get(lang, {"translated": 0, "skipped": 0, "failed": 0})
        print(
            f"  {lang}: translated={bucket['translated']} skipped={bucket['skipped']} failed={bucket['failed']}",
            flush=True,
        )
    print(
        f"\nUsage: model={model} input_tokens={total_input} output_tokens={total_output} "
        f"total_tokens={total_tokens} estimated_cost_usd={total_cost.quantize(Decimal('0.000001'))}",
        flush=True,
    )
    if accepted_models:
        print(f"Accepted models: {', '.join(dict.fromkeys(accepted_models))}", flush=True)
    if substitution_notes:
        print(f"Model substitution: {', '.join(dict.fromkeys(substitution_notes))}", flush=True)

    failures = [r for r in results if r.status == "failed"]
    if failures:
        print("\nFailures:", flush=True)
        for failure in failures:
            print(f"  {failure.target_lang}/{failure.source_file}: {failure.failure}", flush=True)
        return 1
    return 0

def recorded_source_commit(path: Path) -> str | None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    meta = soup.find("meta", attrs={"name": "translation-source-commit"})
    return meta.get("content") if meta else None


def run_check(_: argparse.Namespace) -> int:
    stale: list[tuple[str, str | None, str]] = []
    for lang in NON_ENGLISH:
        lang_dir = REPO_ROOT / lang
        if not lang_dir.exists():
            continue
        for target in sorted(lang_dir.glob("*.html")):
            current_commit = source_commit_for(REPO_ROOT / target.name)
            recorded = recorded_source_commit(target)
            if recorded != current_commit:
                stale.append((str(target.relative_to(REPO_ROOT)), recorded, current_commit))

    if not stale:
        print("No stale translations found.")
        return 0

    for path, recorded, current in stale:
        print(f"{path}: recorded={recorded or 'missing'} current={current}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate static HTML pages into language mirrors.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate = subparsers.add_parser("translate", help="Produce or refresh translations.")
    translate.add_argument("--lang", choices=NON_ENGLISH)
    translate.add_argument("--file", choices=[path.name for path in source_files()])
    translate.add_argument(
        "--only",
        type=parse_only_scope,
        help="Comma-separated non-English language codes or source filenames to translate.",
    )
    translate.add_argument("--force", action="store_true")
    translate.set_defaults(func=run_translate)

    inject_en = subparsers.add_parser("inject-en-metadata", help="Add EN hreflang metadata and language switchers.")
    inject_en.set_defaults(func=run_inject_en_metadata)

    check = subparsers.add_parser("check", help="Report stale translations.")
    check.set_defaults(func=run_check)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
