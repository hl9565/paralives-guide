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

## Queue & brief discipline (collaboration guardrails)

Two writers (this Claude session + the loop-driven session) and one executor (Codex) all touch the queue / handoff files. The rules below close the cracks that have actually been observed.

### Queue insertion rules

- The queue (`briefs/codex-queue.md`) is ordered top-to-bottom by promotion priority.
- When the handoff's OPEN slot is **occupied**, Claude may insert / reorder anywhere, including at #1. Loop will pick up the current #1 only after OPEN frees.
- When the handoff's OPEN slot is **empty**, Claude must not modify #1 (the loop may promote it within the same cycle). Insert new high-priority tasks at #2 and reorder once the previous #1 is in OPEN.
- If a race happens anyway (your "insert at #1" got promoted past), accept the one-cycle delay. Do not race-fight with the loop.

### Brief self-review checklist (before adding a brief to queue)

Run through this mentally before linking a new brief from the queue. No script, no linter — self-discipline.

1. Does §2 "Files affected" exactly match every file path mentioned in §3 "Structural decisions"?
2. Does every entry in §5 "Acceptance criteria" map to a specific §3 decision (no orphan criteria, no §3 decision without a matching criterion)?
3. Does §6 "Out of scope" actually exclude things, not just restate what the brief already covers?
4. Are all files referenced by `if present` / `skip silently` checks really optional, and are the strictly required dependencies named in §3's preflight (where applicable)?
5. Are constraints inherited from `requirements-checklist.md` and skill files referenced, not re-stated? (Avoid drift between briefs and skill.)

If any answer is "no", fix the brief before linking it.

### High-risk brief checkpoint (opt-in)

For briefs that touch 5+ files, restructure existing pages, or carry 10+ acceptance criteria, Claude may insert a `§3.X Checkpoint` requirement in the brief. When present, Codex pauses mid-implementation at the marked point, sets heartbeat status to `awaiting-checkpoint`, and posts a ≤5-line plan for the remaining work. Claude responds with `GO` or `REWRITE` in the handoff review area. The staleness rule does **not** apply to `awaiting-checkpoint` heartbeats. Low-risk briefs (single new page, head-only edits, single-file scripts) do not use checkpoints.

### Brief archival

Once a brief has been implemented, reviewed, and committed, move the brief file itself from `briefs/<name>.md` to `briefs/archive/<name>.md`. This keeps the `briefs/` root scoped to active and pending work. The handoff entry archive (`briefs/handoff-archive/`) remains a separate concept — that one archives heartbeat / report / review snippets per task.

## Current phase pointer

The active phase is tracked in `.claude/skills/write-paralives-article/references/site-quality-target.md` Section 6 — a local-only doc (`.claude/` is gitignored, so this file is not in the public mirror). Read it on the maintainer's working tree before proposing structural work.

## Brand positioning

The site models its information architecture and content strategy after **heartopia.gg** — a comprehensive, helpful, fan-run wiki-and-guides hub. Positioning: "Your Complete Paralives Wiki, Database & Guides for Early Access." Not a wiki we can win on raw breadth, not a YouTube channel we can win on visuals, but a single-maintainer site that earns its place by combining comprehensive coverage with editorial discipline.

Implications, in tension with each other but both binding:

- **Comprehensive**: cover guides, databases, troubleshooting, mods, FAQ, comparisons, news, inspiration, and external resources. Do not narrow into a single niche.
- **Honest**: no subjective "best of" rankings on mods, creators, or external resources. Trust grading separates official-citable sources from community-tier leads. No piracy adjacents, no affiliate-link farms, no padded listicles.

The maintainer does not play Paralives personally. All on-the-ground signal flows through the Paralives Discord (see Discord workflow below). Visuals are sourced from official studio media and Discord screenshots with attribution, never from invented descriptions.

## Discord workflow (signal source)

Because the maintainer does not play the game, the Paralives Discord is the primary source of in-game observation. The workflow is:

1. Maintainer reads Discord regularly (target: ~30–60 min/week, sweeping announcements, bug-reports, dev-talk).
2. When the maintainer sees something useful — a bug report with evidence, a confirmed feature detail, a screenshot worth using — they paste it (text and/or image) into the active Claude Code session.
3. Claude Code structures the signal into `briefs/discord-signals.md` using the entry format defined in that file. Images go under `assets/discord/YYYY-MM-DD-slug.ext`.
4. Codex implementations reference `briefs/discord-signals.md` when relevant. Entries are **community-tier by default** — citable in article body only when their `Confirmed by` field points to an official paralives.com / Steam / studio URL.

This workflow is **load-bearing for brand positioning**. If the Discord-scanning cadence drops to zero, content will go stale, factual claims will rot, and the "comprehensive companion" stance becomes hollow. Treat it as a recurring obligation, not an ad-hoc task.

Image rules, attribution requirements, and the full entry format are documented in `briefs/discord-signals.md`. Codex must follow that file's rules whenever it embeds Discord-sourced material in HTML.
