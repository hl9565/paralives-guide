# Project workflow — role split

**Claude Code in this project does architecture and design only. Coding is done by Codex.**

## What Claude Code does here

- Information architecture, site structure, page hierarchy, navigation design.
- Phase planning, roadmap maintenance, scope decisions.
- Content strategy: what guides / databases / tools to add and in what order.
- Reviewing Codex's output against the architectural intent.
- Writing and maintaining skill files under `.claude/skills/write-paralives-article/` (project-local skill files).

## What Claude Code does NOT do here

- **Do not edit project source files**: `*.html`, `deploy.sh`, `init.sh`, `CNAME`, CSS, JS, or any file under the project root. Codex writes these.
- Do not run `./deploy.sh` or push against this repo. Codex or the maintainer deploys.
- Claude Code may create local git commits only when the handoff/review workflow says the completed Codex output is reviewed and ready to commit, the changed files are within the reviewed scope, and the working tree has no unrelated or suspicious changes. If in doubt, ask before committing.
- Do not write content for articles, even drafts in markdown. Hand the brief to Codex.

**Exception — Claude Code may write:** `CLAUDE.md` itself, and any file under `briefs/`. These are architectural documents, not source code.

## Hand-off format

When a piece of work is ready for Codex, Claude Code writes a **design brief** as a markdown file under `briefs/<phase-or-task-slug>.md` containing:

1. **Goal** — one sentence: what the user will see / be able to do after this change.
2. **Files affected** — exact paths, marked `new` / `edit` / `delete`.
3. **Structural decisions** — nav layout, page slots, schema fields, link wiring. The things that need *thinking*, not typing.
4. **Constraints inherited from skill** — point to `.claude/skills/write-paralives-article/references/site-quality-target.md` and the relevant phase, plus any anti-patterns that apply.
5. **Acceptance criteria** — what Codex's output must satisfy to be considered done.
6. **Out of scope** — explicit list of what NOT to change, to prevent drift.

### Handing the brief to Codex

Open Codex Desktop on this project directory and use this prompt template:

```
Read CLAUDE.md and briefs/<brief-name>.md.
Implement the brief exactly. Honor all constraints and the "Out of scope" list.
Do not edit files outside the brief's "Files affected" section.
When done, summarize what changed and stop — do not deploy.
```

After Codex finishes, return to Claude Code and ask for a review against the brief. Once review passes, run `./deploy.sh "<message>"` (manually or via Codex) to ship.

## Current phase pointer

The active phase is tracked in `.claude/skills/write-paralives-article/references/site-quality-target.md` Section 6 — a local-only doc (`.claude/` is gitignored, so this file is not in the public mirror). Read it on the maintainer's working tree before proposing structural work.
