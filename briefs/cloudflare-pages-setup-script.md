# Brief — Cloudflare Pages Setup Script

## 1. Goal

After this brief lands, the project has a reusable local script that can push the current `main` branch to the already-created private GitHub repo and deploy the static site to Cloudflare Pages with as little manual Dashboard work as possible.

## 2. Files affected

**New**

- `scripts/setup-pages.sh` — local operational helper for GitHub remote/push plus Cloudflare Pages deployment via Wrangler.

**Edit**

- `.gitignore` — only if needed to ignore local Wrangler or Cloudflare artifacts created by the script. Do not add broad ignores that could hide source files.

**Do not touch**

- `.claude/skills/**` — read-only for Codex. Skill files are Claude's territory per `CLAUDE.md`.
- `briefs/**` — read-only for Codex. Codex implements briefs; Claude writes them.
- `index.html`, `_headers`, `CNAME`, `robots.txt`, `deploy.sh`, `.env.example`, `scripts/translate.py` — this task is operational tooling only; do not change site content, deploy flow, identity tokens, or translation code.

## 3. Structural decisions

### 3.A — Automation model

Use a shell script instead of embedding this into `deploy.sh`.

Reason: `deploy.sh` is the post-setup publishing path and must stay minimal. `scripts/setup-pages.sh` is a one-time or occasional environment setup helper.

### 3.B — GitHub remote behavior

The GitHub repository already exists:

```text
https://github.com/hl9565/paralives-guide
```

The script should:

1. Require it to be run from inside the project checkout, but use `git rev-parse --show-toplevel` so it does not depend on the user's current working directory.
2. Verify the current branch is `main`; if not, fail with a clear message.
3. Verify `gh` is installed and authenticated (`gh auth status`).
4. If `origin` does not exist, add:
   ```text
   https://github.com/hl9565/paralives-guide.git
   ```
5. If `origin` exists and already points to that URL, continue.
6. If `origin` exists and points somewhere else, fail and print the existing URL. Do not overwrite it automatically.
7. Push with:
   ```bash
   git push -u origin main
   ```

Do not create the GitHub repository; Claude already created it and reported the URL.

### 3.C — Cloudflare Pages behavior

Prefer Cloudflare's official Wrangler CLI.

The script should support direct Pages deployment of the static root, because fully connecting Cloudflare Pages to GitHub usually requires first-time Dashboard authorization of the Cloudflare GitHub App.

Default project name:

```text
paralives-guide
```

The script should:

1. Verify Node/npm availability if it plans to use `npx wrangler`.
2. Verify Cloudflare auth using Wrangler. If not authenticated, print a clear instruction such as:
   ```bash
   npx wrangler login
   ```
   and stop.
3. Create the Pages project if it does not already exist, using production branch `main`.
4. Deploy the project root as a static Pages deployment.
5. Print the resulting Pages URL from Wrangler output or, if Wrangler does not provide a parseable URL, print the project name and the Cloudflare Dashboard follow-up step.

Use `npx wrangler` unless a local dependency is already present. Do not add npm dependencies or create `package.json` just for this helper.

### 3.D — Custom domain boundary

Do not attempt to modify DNS or registrar settings.

Domain policy:

- `paralivesguide.help` is the primary canonical domain for this site.
- `paralives.help` is a secondary alias and should 301 redirect to `https://paralivesguide.help/`.

After deployment, print the manual follow-up:

```text
In Cloudflare Pages, add paralivesguide.help as the primary custom domain for project paralives-guide if it is not already attached.
Then attach paralives.help only as a redirect alias to https://paralivesguide.help/; do not make it a second canonical site.
```

If Wrangler has a stable command for custom domains or redirect rules in the installed version, the script may print it as an optional command, but must not run it automatically unless the command is verified locally and still requires the user's Cloudflare account authorization.

### 3.E — Script safety and UX

The script should be safe to re-run.

Requirements:

- `#!/usr/bin/env bash`
- `set -euo pipefail`
- Clear status lines before each major action.
- Clear error messages to stderr.
- No destructive git commands.
- No `git add`, no `git commit`, no force push.
- Do not run `./deploy.sh`.
- Do not write secrets.
- Do not create or modify `.env`.
- Do not install global packages.
- Keep all paths rooted at the git top-level directory.

Recommended flags:

- `--github-only` — only configure origin and push.
- `--cloudflare-only` — only run the Wrangler deployment.
- `--skip-push` — configure/check remote but do not push.
- `--help` — show usage.

Keep argument parsing simple; no external dependencies.

## 4. Constraints inherited from skill

This brief is not an article-writing task, but the project role split in `CLAUDE.md` still applies:

- Claude writes the brief.
- Codex writes the script.
- Codex must not edit `.claude/skills/**` or `briefs/**`.
- Codex must not deploy via `./deploy.sh`.

Operational constraints:

- Do not change the Phase 0 site shell.
- Do not change identity tokens, domain, palette, metadata, or copy.
- Do not touch AdSense placeholders.
- Do not alter `scripts/translate.py`.

## 5. Acceptance criteria

Codex's output is acceptable when:

1. `scripts/setup-pages.sh` exists and is executable.
2. The script can be run from any subdirectory inside the repo because it resolves the git top-level path.
3. Re-running the script does not duplicate remotes or overwrite an unexpected `origin`.
4. The script fails safely if GitHub CLI, Wrangler auth, Node/npm, or Cloudflare auth are missing.
5. The script pushes only `main` to `origin`; it does not stage, commit, amend, force-push, or deploy through `deploy.sh`.
6. The script uses Wrangler for Cloudflare Pages direct deployment of the static root.
7. The script prints the manual custom-domain follow-up for `paralivesguide.help` as primary and `paralives.help` as a redirect alias.
8. No files outside the "Files affected" section are modified.

## 6. Out of scope

- Do not create a new GitHub repository.
- Do not connect Cloudflare Pages to GitHub through the Dashboard.
- Do not configure DNS records or registrar settings.
- Do not add a build system.
- Do not add npm project files solely for Wrangler.
- Do not change `deploy.sh`.
- Do not edit site HTML, content, CSS, metadata, headers, robots, or translation code.
- Do not deploy automatically while implementing the script unless the user explicitly asks Codex to run it after review.

## 7. Prompt for Codex

Open Codex Desktop on this project directory and use:

```text
Read CLAUDE.md and briefs/cloudflare-pages-setup-script.md.
Implement the brief exactly. Honor all constraints and the "Out of scope" list.
Do not edit files outside the brief's "Files affected" section.
When done, summarize what changed and stop — do not deploy.
```
