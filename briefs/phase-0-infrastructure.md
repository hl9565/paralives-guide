# Brief — Phase 0: Infrastructure + Identity Lock

## 1. Goal

After this brief lands, https://paralivesguide.help serves a branded "Paralives Guide" placeholder page through Cloudflare Pages, and the project has every piece of scaffolding in place — git remote, deploy pipeline, role-split documentation, translation pipeline copy, locked identity tokens — so that Phase 1 (information architecture) can begin by editing files instead of bootstrapping them.

## 2. Files affected

**New** (project root: `/Users/huanglin/web/paralives/`)

- `CLAUDE.md` — role split inherited from zero-parades, paths updated.
- `deploy.sh` — minimal: `git add -A && git commit -m "$1" && git push`.
- `.gitignore` — standard + `.env` + `.DS_Store` + `.venv` + `__pycache__`.
- `.env.example` — template for translation API credentials. **Do not commit a populated `.env`.**
- `CNAME` — single line: `paralivesguide.help`.
- `_headers` — Cloudflare Pages headers config, copied verbatim from `/Users/huanglin/web/zero-parades/_headers`.
- `robots.txt` — allow all crawlers, no sitemap reference yet (Phase 1.5 generates it).
- `scripts/translate.py` — **copied byte-verbatim** from `/Users/huanglin/web/zero-parades/scripts/translate.py`. Do not edit `LANGS` in this phase; Phase 1.5 brief sets it.

**Edit**

- `index.html` — replace the existing MVP draft with the Phase 0 reference shell described in §3.B. The MVP was a Chinese-language sketch; the Phase 0 shell is English (root locale per §5a), uses locked tokens, and serves as the structural reference that Phase 1 builds the dashboard out of.

**Do not touch**

- `.claude/skills/**` — read-only for Codex. Skill files are Claude's territory per `CLAUDE.md`.
- `briefs/**` — read-only for Codex. Codex implements briefs; Claude writes them.

## 3. Structural decisions

### 3.A — Directory layout (final after this brief)

```
/Users/huanglin/web/paralives/
├── CLAUDE.md
├── CNAME
├── _headers
├── deploy.sh
├── .env.example
├── .gitignore
├── index.html                 ← Phase 0 reference shell
├── robots.txt
├── briefs/                    ← Claude-only, read-only for Codex
│   └── phase-0-infrastructure.md
├── scripts/
│   └── translate.py           ← copied verbatim from zero-parades
└── .claude/                   ← Claude-only
    ├── settings.local.json
    └── skills/
        └── write-paralives-article/
            ├── SKILL.md
            └── references/
                ├── article-template.md
                ├── requirements-checklist.md
                └── site-quality-target.md
```

### 3.B — `index.html` Phase 0 reference shell

A single self-contained file that locks every identity token. Phase 1 will expand this same file into a dashboard; the locked `<head>`, `<style>`, topbar shell, and footer copy verbatim into every future article.

**`<head>` requirements (binding):**

- `<meta charset="UTF-8">`, viewport.
- `<title>Paralives Guide — Fan resource for the cozy life sim</title>`
- `<meta name="description" content="Paralives Guide is a fan resource for Paralives, the cozy life-sim from Paralives Studio. Build guides, character creation, traits, and community house designs — all updated against the current Early Access build.">`  (170 chars; matches §4 SEO rules).
- `<link rel="canonical" href="https://paralivesguide.help/">`.
- Google Fonts preconnect + stylesheet for **Fraunces** (display, weights 400 / 600 / 700) and **Inter** (body, weights 400 / 500 / 600 / 700).
- AdSense `<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=[[ADSENSE_CLIENT]]" crossorigin="anonymous"></script>` — **commented out with a TODO** at this phase; uncomment + populate when AdSense application is approved (post-Phase-1).
- `<style>` block locking the palette and base typography (see 3.C).

**`<body>` structure:**

```html
<header class="topbar">
  <div class="brand"><a href="/">Paralives<span> </span>Guide</a></div>
  <!-- nav added in Phase 1 — do not add placeholder links here -->
</header>

<main class="wrap">
  <section class="hero">
    <p class="kicker">A fan resource</p>
    <h1>Paralives Guide</h1>
    <p class="lede">
      A cozy, opinionated, build-aware companion for <em>Paralives</em>, the indie life sim
      from Paralives Studio. Guides, databases, and small tools — fully open, written by
      players who actually log the hours.
    </p>
    <p class="note">
      The site is just getting started. Hubs and the first guides arrive in the next update.
    </p>
  </section>
</main>

<footer class="site-footer">
  <div class="brand">Paralives<span> </span>Guide</div>
  <p class="disclaimer">
    Paralives is a trademark of Paralives Studio. This is an unaffiliated fan resource;
    nothing here is endorsed by or affiliated with Paralives Studio.
  </p>
  <!-- language switcher slot — empty at Phase 0, populated in Phase 1.5 -->
  <div class="lang-switcher" aria-hidden="true"></div>
</footer>
```

**No nav links, no route cards, no featured-guide cards, no scale signal strip at this phase.** Phase 1 brief adds them.

### 3.C — Locked CSS (must appear in `<style>` block verbatim)

```css
:root {
  --cream:      #fdf6ec;
  --pink:       #f4c8c0;
  --pink-deep:  #e89a8e;
  --sage:       #b8c9a7;
  --sage-deep:  #7a9269;
  --ink:        #3d3530;
  --ink-soft:   #6b5d54;
  --line:       #ead9c8;
  --shadow:     0 4px 16px rgba(61, 53, 48, 0.06);
  --shadow-hover: 0 8px 28px rgba(61, 53, 48, 0.12);

  --font-display: "Fraunces", Georgia, "Times New Roman", serif;
  --font-body:    "Inter", -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

body {
  font-family: var(--font-body);
  background: var(--cream);
  color: var(--ink);
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3 {
  font-family: var(--font-display);
  letter-spacing: -0.01em;
  color: var(--ink);
}
```

(Codex may add styling for `.topbar / .brand / .wrap / .hero / .kicker / .lede / .note / .site-footer / .disclaimer / .lang-switcher` as needed to render the Phase 0 page cleanly. Keep CSS lean — Phase 1 will add the dashboard styles.)

**Anti-patterns to enforce in CSS (from `article-template.md`):**
- Do not use pure white `#fff` as background; cream is the brand.
- Do not use stencil / monospace display type for headings; reserve monospace for `.kicker` glyph codes and factbox keys (Phase 1+).
- No dark-mode override at this phase.

### 3.D — `CLAUDE.md` content

Adapt zero-parades' `CLAUDE.md` byte-for-byte, with these substitutions:

- All `zero-parades` → `paralives`
- `zeroparadesguide.wiki` → `paralivesguide.help`
- `~/.claude/skills/write-zeroparades-article/` → `.claude/skills/write-paralives-article/` (project-local path — different from zero-parades' written convention; our skill lives in-repo)
- Reference brief path: `briefs/<phase-or-task-slug>.md` (unchanged)
- "current phase pointer" link target: `.claude/skills/write-paralives-article/references/site-quality-target.md` Section 6

Otherwise keep all role-split rules, brief format, hand-off prompt template, and deploy flow identical.

### 3.E — `deploy.sh` content

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "usage: ./deploy.sh \"<commit message>\""
  exit 1
fi

git add -A
git commit -m "$1"
git push
```

`chmod +x deploy.sh`. No `git status` check loop, no fancy logging — keep parity with zero-parades' deploy script.

### 3.F — `scripts/translate.py` copy

Copy `/Users/huanglin/web/zero-parades/scripts/translate.py` byte-verbatim into `/Users/huanglin/web/paralives/scripts/translate.py`. Do **not**:
- Edit the `LANGS` list.
- Edit the proxy URL or model name.
- Edit any of the subcommand implementations (`translate`, `inject-en-metadata`, `check`).

The Phase 1.5 brief is the only place those values change. Phase 0 just gets the file on disk so the project has the dependency declared.

If `scripts/__init__.py` exists in the source, copy it too. If a `requirements.txt` or `pyproject.toml` exists at the zero-parades root that the script imports, copy it.

### 3.G — `.env.example` content

```
# Translation pipeline credentials — copy this file to .env and fill in real values.
# Do not commit .env.

OPENAI_API_BASE=http://115.238.140.58:6015/v1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4
```

Codex should not invent new key names — these are the ones `scripts/translate.py` expects (verify by reading the copied script).

### 3.H — Git remote + Cloudflare Pages connect

This sub-section is **operational, not code-editing**. Codex should:

1. `git init` at project root if not already initialised.
2. Stage everything **except** `.env`, `.DS_Store`, `.venv`, `__pycache__`, and any leftover MVP scratch files.
3. Initial commit message: `"Init: Phase 0 — infrastructure + identity lock"`.
4. **Stop and surface to the user**: "Create a new GitHub repository (private, name suggested: `paralives-guide`) and report the remote URL. Then I'll add the remote, push, and connect Cloudflare Pages."

Codex must NOT:
- Create a GitHub repo on behalf of the user (no `gh repo create`).
- Connect Cloudflare Pages directly (CF auth lives outside Codex's reach).
- Configure DNS for `paralivesguide.help` (user's registrar account).

User completes git-remote + CF Pages + DNS manually after Codex hands off; this is the same pattern zero-parades used.

### 3.I — `robots.txt` content

```
User-agent: *
Allow: /

# Sitemap will be added in Phase 1.5 once translation pipeline emits it.
```

### 3.J — `_headers` content

Copy verbatim from `/Users/huanglin/web/zero-parades/_headers`. If the zero-parades file has site-specific paths in it, Codex should flag those for review rather than silently rewriting.

## 4. Constraints inherited from skill

- **Voice & tone**: `.claude/skills/write-paralives-article/references/requirements-checklist.md` §3. The Phase 0 hero copy ("A cozy, opinionated, build-aware companion …") is the *first* prose on the site — it sets voice for every future article. Do not soften it into marketing copy ("Discover everything you need to know…") or stiffen it into noir.
- **HTML structure**: `requirements-checklist.md` §2. Phase 0 `index.html` doesn't yet have a `.kicker / h1 / byline / TOC / sections / FAQ / related-grid` body (that's article-shape, not landing-shape) — but the `<head>` requirements (canonical, meta description, fonts, AdSense placeholder) all apply.
- **SEO**: `requirements-checklist.md` §4. Title under 60 chars ✓ (currently 47). Meta description 140–170 chars ✓.
- **Out of scope rules**: `requirements-checklist.md` §7. No analytics SDKs, no chat widgets, no comment systems, no JavaScript beyond what AdSense and the (future) language switcher require.
- **Anti-patterns**: `site-quality-target.md` §7. Pay particular attention to:
  - "Don't fragment a language family" — no `zh-TW` / `pt-PT` / `es-ES` in any future config.
  - "Don't accept user-submitted content without verification" — irrelevant at Phase 0 but locked in.
- **Identity tokens**: every locked value in `site-quality-target.md` §4 is binding. Do not substitute "fonts that look similar" or "a slightly different cream". Use exact values.

## 5. Acceptance criteria

- [ ] All "New" files in §2 exist at the listed paths with the contents described.
- [ ] `index.html` is the Phase 0 reference shell described in §3.B (English, `Paralives Guide` brand, Fraunces + Inter fonts, locked palette, AdSense commented-out placeholder, footer disclaimer, language switcher slot present but empty).
- [ ] `CLAUDE.md` mirrors zero-parades' role-split with the substitutions in §3.D.
- [ ] `deploy.sh` is executable (`chmod +x` applied).
- [ ] `scripts/translate.py` is byte-identical to the zero-parades source (verify with `diff` or `cmp`).
- [ ] `.gitignore` excludes `.env`, `.DS_Store`, `.venv`, `__pycache__`.
- [ ] No `.env` file is committed; `.env.example` is committed.
- [ ] `CNAME` contains exactly `paralivesguide.help` (no trailing whitespace, no www).
- [ ] First git commit message is `Init: Phase 0 — infrastructure + identity lock`.
- [ ] Codex has surfaced the GitHub-repo / CF-Pages / DNS handoff message to the user (3.H step 4) and stopped — has **not** attempted to create the remote, deploy, or change DNS.
- [ ] No file under `briefs/` or `.claude/skills/` was modified by Codex.

## 6. Out of scope

- Do **not** add a topbar nav. Phase 1 brief adds the 6-link nav (`Guides · Database · Tools · Houses · Updates · About`).
- Do **not** add route cards, featured-guide cards, or the scale signal strip. All Phase 1.
- Do **not** create `guides.html`, `database.html`, `tools.html`, `houses.html`, or any other hub page. All Phase 1.
- Do **not** generate any translated mirrors under `/<lang>/`. All Phase 1.5.
- Do **not** apply for AdSense, populate `[[ADSENSE_CLIENT]]`, or uncomment the AdSense `<script>` tag. Deferred to post-Phase-1.
- Do **not** add Google Analytics, Plausible, Fathom, or any other analytics SDK.
- Do **not** add a favicon, app icons, or social card images. These are nice-to-haves but not Phase 0 blockers; user will provide assets in a later brief.
- Do **not** edit `.claude/skills/**` or `briefs/**` — they are Claude's territory per `CLAUDE.md`.
- Do **not** invent additional identity tokens (extra colour variables, alternate fonts, secondary brand wordmark). The §4 table in `site-quality-target.md` is the authoritative list.
- Do **not** run `./deploy.sh` from Codex. Deploy happens after user wires up the GitHub remote + CF Pages manually.

## 7. After Codex finishes

1. Codex reports the diff (list of new files, single edit to `index.html`) and stops.
2. User reviews against this brief. Specifically check:
   - `index.html` renders cleanly in a browser (open the local file).
   - Brand, fonts, palette match the locked tokens visually.
   - `scripts/translate.py` is byte-identical to source (`cmp /Users/huanglin/web/zero-parades/scripts/translate.py /Users/huanglin/web/paralives/scripts/translate.py` returns nothing).
3. User creates the private GitHub repo (suggested name: `paralives-guide`), adds the remote, pushes.
4. User connects Cloudflare Pages to the repo, sets build settings (none — pure static), points DNS for `paralivesguide.help`.
5. First production deploy: `./deploy.sh "Init: Phase 0 — infrastructure + identity lock"` (no-op if already pushed in step 3; otherwise this is the first push).
6. Verify https://paralivesguide.help renders the Phase 0 shell.
7. Return to Claude Code. Update `site-quality-target.md` §6: move Phase 0 to "completed (YYYY-MM-DD)" and write the new active-phase block pointing at `briefs/phase-1-ia-upgrade.md`. Update §4 with the AdSense application status (pending or submitted).
