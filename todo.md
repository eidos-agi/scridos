# Upgrading scridos: a substantive proposal

Context — what scridos is today vs what we've learned operating it

scridos right now is the upstream ekadetov/llm-wiki fork: six operations (init, ingest, compile, query, lint, remove), Obsidian-vault-only discovery (`~/ObsidianVault/03-Resources/<name>/`), a flat `wiki/` directory, optional qmd BM25+vector search, and Karpathy's pattern in prose form.

Operating it on cerebro-wiki for one day surfaced specific gaps. Every upgrade below is anchored to a real failure mode caught today, not a speculative wish.

---

## I. Rebrand (the cosmetic baseline)

The mechanical issue I tried to short-circuit earlier. Files in upstream eidos-agi/scridos:

- `.claude-plugin/plugin.json` — `name: "llm-wiki"` → `"scridos"`, author → Eidos AGI
- `.claude-plugin/marketplace.json` — same
- `commands/wiki.md` — skill ref `llm-wiki:wiki` → `scridos:wiki`
- `skills/wiki/SKILL.md` — every `/llm-wiki:wiki` example
- `scripts/install-deps.sh` — `[llm-wiki]` log prefix
- `README.md` + `WALKTHROUGH.md` — title, install/uninstall, all examples, plugin data-dir paths
- Preserve: "LLM Wiki pattern" wherever it refers to Karpathy's named pattern; preserve the `ekadetov/llm-wiki` upstream attribution in README

This is the smallest commit. Everything below is the actual upgrade.

---

## II. KPIs for a scribe (the measurement spine)

A scribe is the agent operating scridos. Without measurable success criteria, "is the wiki good?" is rhetorical. I propose six KPIs grouped by what they protect against. These become what `scridos:wiki grade` reports.

### 1. Faithfulness — does every claim trace to a source?

- **Provenance coverage** = (compiled pages with `source:` frontmatter pointing to a file in `raw/`) / (total compiled pages). Target ≥ 95%. Concept pages synthesized from multiple sources are exempt but must list `sources: [a, b, c]`.
- **Citation density** = wikilinks-per-100-words on synthesized pages. Target ≥ 3. Below this and the page is asserting without citing.

### 2. Cohesion — does the wiki form a graph, not a pile?

- **Backlink reach** = (pages with ≥ 1 inbound link) / (total pages). Target ≥ 90%. Orphan rate is the inverse.
- **Average page degree** = mean(inbound + outbound wikilinks per page). Target ≥ 4. Below this, the graph isn't dense enough to compound.

### 3. Currency — is the wiki a snapshot of now, not 90 days ago?

- **Stale-page count** = pages with `status: stale` OR `last-confirmed: <90+ days>`. Target = 0 untriaged stale pages.
- **Age distribution** = histogram of last-confirmed ages. Surface as a sparkline in the grade report.

### 4. Hierarchy — is knowledge findable by walking the tree?

- **Domain coverage** = (numbered domain folders with non-empty `_index.md`) / (total domain folders). Target = 100%.
- **Index parity** = `wiki/index.md` entries match actual files (no drift in either direction). Target = 0 mismatches.

### 5. Doctrine compliance — does the wiki narrate vs duplicate?

- **No-redundant-spec check**: wiki pages whose body duplicates content already canonical in code (e.g., per-metric wiki pages when `<metric>.py` exists in a registry). The wiki-points-code-defines doctrine says these violations are bugs. Target = 0.
- **Procedural-overview check**: each domain `_index.md` should be procedural (narrative + cross-links), not a re-implementation of the canonical artifact.

### 6. Compounding — does each ingest enrich existing pages, not just add new ones?

- **Compile fan-out** = mean(pages-touched-per-ingest). Target ≥ 3. If every ingest only writes one new page and updates nothing, the wiki is appending, not compounding.

These six KPIs are exactly what `cerebro-wiki/tools/grade.py` already measures for cerebro-wiki. I'd promote `grade.py` to a scridos operation (see VIII below).

---

## III. Provenance as a first-class concept

Today: compile writes pages but doesn't enforce provenance. Frontmatter has `source-url:` on source-summaries but concept pages have nothing — they read as confident assertion-statements with no link back to where the claim came from.

Proposal: extend the schema in `CLAUDE.md` (the per-wiki schema) so every compiled page carries:

```yaml
---
date: 2026-04-29
type: concept
sources:
  - raw/articles/2026-04-29-paylocity-2pm-meeting-outcomes.md
  - raw/articles/2026-04-29-karpathy-llm-wiki-canonical.md
last-confirmed: 2026-04-29
confidence: stakeholder-confirmed | derived | inferred
---
```

Three new mechanics scridos should enforce:

1. **compile writes `sources:` automatically** — it knows which raw file(s) it pulled the concept from. Today it just doesn't record this.
2. **lint flags missing provenance** — concept pages with no `sources:` array AND no body links to `raw/articles/` get flagged. (Counter-arguments: pages legitimately distill multiple sessions of context with no single source. These should mark `confidence: derived` and link to whatever the closest written record is.)
3. **query cites at the page level, not just at the wikilink level** — the answer's bibliography lists the underlying raw sources, transitively followed through the wiki pages. Right now query cites the wiki page; users need one more click to see the actual evidence.

The KPI-1 measurement (Faithfulness) is computed against this schema.

---

## IV. Maintenance — keep the wiki from rotting

Today's lint checks orphans, dead links, missing "Counter-Arguments and Gaps" sections, stale `status: stale` markers, index drift. Useful. Insufficient.

Add four maintenance behaviors:

### 1. Decay model

Every page gets `last-confirmed: YYYY-MM-DD`. lint surfaces a triage list: pages older than N days (default 90) where the underlying source is also older than N days. The scribe's job is to either mark `last-confirmed: <today>` after a re-read or mark `status: stale` and link to what would refresh it. Bias: confirm cheaply, flag expensively.

### 2. Re-ingest detection

When ingest is called on a path that's a newer revision of an already-ingested source (same vendor, similar slug, newer date), scridos should detect the relationship rather than treat it as a fresh source. Today re-ingesting `Greenmark_Metrics_2.11.26.pdf` and later `Greenmark_Metrics_3.20.26.pdf` would create two unrelated source-summaries; the scribe wants a "supersedes" relationship: new source-summary, old one marked `superseded-by:`, downstream concept pages refreshed against the new source.

### 3. Watchlist

A wiki-level `watchlist.md` lists topics, sources, or stakeholders whose updates would invalidate downstream pages. When a new ingest touches a watchlist entry, compile lists "pages that may need refresh because <thing> changed." The scribe doesn't auto-edit; the scribe gets a punch list.

### 4. Lint regression report

lint writes `outputs/reports/YYYY-MM-DD-lint.md` (already does). Diff-from-last-lint is what's missing — "this lint run found 22 broken wikilinks; last run found 18; here are the 4 that regressed." Otherwise, lint reports are point-in-time and you can't tell if the wiki is improving or rotting.

These four maintenance behaviors operationalize KPI-3 (Currency).

---

## V. Tree-organized wikis (numbered domain folders)

Today: `wiki/` is flat. Karpathy's gist showed a flat layout; that's fine for a single-topic wiki. cerebro-wiki proved that for multi-domain knowledge bases (vendors / architecture / metrics / stakeholders / substrate / decisions / meetings / entities) you need a tree. A flat 100-page wiki is unnavigable.

Proposal: scridos natively supports tree wikis.

- `init <name> --tree <8>` (or `--domains "vendors,architecture,..."`) creates `wiki/01-vendors/`, `wiki/02-architecture/`, ..., each with an `_index.md` stub
- compile accepts a `--domain <name>` hint to route the new pages into the right folder, and infers the domain from frontmatter `tags:` if not given
- The schema in `CLAUDE.md` documents the tree shape and routing rule (which goes where)
- query walks the tree: read domain `_index.md` files first to identify candidate domains, then read pages within
- Wikilinks resolve by filename across folders (Obsidian behavior) — already works

The KPI-4 measurement (Hierarchy) presupposes this tree exists.

---

## VI. Web viewer (`scridos:wiki serve`)

Today: wikis are browsable in Obsidian (rich) or via raw GitHub render (flat). Neither works for stakeholders who don't want to install Obsidian, can't access the private GitHub repo, or want a clean Wikipedia-style read.

I built `tools/web/serve.py` (~150 lines, Flask + mistune) inside cerebro-wiki today. Promote it to scridos:

- `scridos:wiki serve [--port 5000] [--public]` starts a Flask server in the active wiki
- Sidebar = the tree; top breadcrumbs; `[[wikilinks]]` resolved by filename; `/search?q=` substring across all pages
- Read-only; no edit endpoint (preserves "Obsidian/git is the editor" model)
- `--public` flag deploys to a public URL via something like cloudflared tunnel (off by default; the wiki is private by default)

This pulls a useful pattern out of cerebro-wiki and into scridos, where it's reusable for any future wiki.

---

## VII. Wiki-points-code-defines doctrine (lint extension)

Today's lint doesn't know about external canonical sources. cerebro-wiki has a doctrine (`[[definitional-hierarchy]]`) that says: when there's a registry of N atomic things in code (e.g., 95 metrics each as a `.py` file), the wiki narrates and cross-links — it does NOT replicate. Per-metric wiki pages would be a doctrine violation.

Proposal: `CLAUDE.md` schema gets a new section:

```yaml
canonical-sources:
  - path: ../data-daemon-v4/registry/proofs/
    pattern: "*.py"
    domain: "03-metrics"
    rule: "wiki narrates; do not create per-metric pages here"
```

lint enforces this: if a wiki page's filename matches an entry in the canonical source, flag it. KPI-5 (Doctrine compliance) measures this.

This is the `grade.py` "Doctrine compliance" dimension, formalized.

---

## VIII. `scridos:wiki grade` (promote `grade.py` upstream)

Today: `grade.py` lives in `cerebro-wiki/tools/grade.py`, which is fine for cerebro-wiki but means every wiki has to re-implement it.

Promote to scridos as a 7th operation:

- `scridos:wiki grade` reads the same six KPIs (II above), produces a markdown scorecard at `outputs/reports/YYYY-MM-DD-grade.md`
- Letter grades A/B/C/D/F per dimension + overall; trend line vs last grade
- `--canonical-source <path>` flag points the doctrine-compliance check at the external code registry (e.g., `../data-daemon-v4/registry/proofs/`)
- `--threshold <grade>` exit code (so grade can gate CI: "fail if wiki dropped below B")

This makes the KPIs operational, not aspirational.

---

## IX. Discovery beyond Obsidian

Today: init creates wikis at `~/ObsidianVault/03-Resources/<name>/`; the active-wiki walk-up assumes that root. cerebro-wiki sits at `~/repos/cerebro-wiki/`, NOT inside Obsidian. The walk-up still works (cwd-anchored), but init doesn't.

Proposal: `init <name> --location <path>` accepts an arbitrary path. Default still `~/ObsidianVault/03-Resources/<name>/` for backward compatibility. The active-wiki walk-up already works for both.

This is what unblocked cerebro-wiki today; it should be a first-class option, not a workaround.

---

## X. Compatibility, scope split, and migration

### What goes upstream (back to ekadetov)

- The rebrand of internal identifiers (no — that's our fork's brand; ekadetov keeps llm-wiki)
- The discovery-beyond-Obsidian change (IX) — broadly useful, no eidos-specific concepts
- Provenance frontmatter (III) — broadly useful
- Decay model (IV.1) and re-ingest detection (IV.2) — broadly useful

### What stays in the eidos scridos fork

- KPIs framework + grade operation (II, VIII) — opinionated; ekadetov may not want this complexity
- Tree support (V) — opinionated; some users want flat
- Web viewer (VI) — separate concern; could be its own plugin
- Doctrine compliance lint (VII) — opinionated and tied to the wiki-points-code-defines pattern

### Migration plan for cerebro-wiki

1. Rebrand lands; cerebro-wiki keeps working (slash command changes from `/llm-wiki:wiki` to `/scridos:wiki` — README + skills update accordingly)
2. Provenance frontmatter retro-applied to the 19 existing pages (one batch, ~1 hour)
3. `grade.py` deletes from `cerebro-wiki/tools/` and `scridos:wiki grade` is invoked instead
4. `tools/web/serve.py` deletes from `cerebro-wiki/tools/` and `scridos:wiki serve` is invoked instead
5. Tree support is already present in cerebro-wiki (8 numbered domains); scridos formalizes the schema

### What I would NOT do

- Do not make scridos editable (read-only Obsidian/git stays the editor)
- Do not add a database (wiki = markdown files; that's the point)
- Do not add auth (wiki is private-by-default; if someone wants public, `serve --public` deploys behind their tunnel)
- Do not add an LLM-call cache (query should always re-read; freshness > speed)

---

## Issue routing — what gets filed where

If you green-light this proposal, I'd file it as one tracking issue at `eidos-agi/scridos` linking to eight sub-issues (one per upgrade I–VIII; IX folds into III). The rebrand (I) is the unblocker; everything else can land independently. Each sub-issue is a contract: title, motivation (failure-mode caught), acceptance criteria, files-touched.

What I'd want from you to proceed:

1. Yea/nay on each upgrade (especially V tree, VI web viewer, VII doctrine — these are the most opinionated)
2. Path to filing issues at `eidos-agi/scridos` — either add it to cerebro-github's TIER_MAP, or whitelist non-Greenmark orgs in ceremony-guard, or you file the tracking issue and I file the sub-issues against it
3. Any KPI you'd add or drop — six is what I picked; you may have stakeholder-driven ones I'm missing (e.g., "is Daniel finding what he needs in <30 seconds?" which is hard to measure but is the actual goal)
