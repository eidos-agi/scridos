# scridos

A Claude Code plugin that builds persistent, compounding knowledge bases inside Obsidian using Karpathy's LLM Wiki pattern. Ingest sources, query synthesized knowledge, lint for gaps — all from your Claude Code session.

> Forked from [ekadetov/llm-wiki](https://github.com/ekadetov/llm-wiki). Renamed and extended for the Eidos AGI ecosystem.

## Installation

```bash
claude plugin install /path/to/scridos
```

### Prerequisites

- **Node.js 18+** — for automatic qmd and Marp installation
- **Git** — for auto-committing wiki changes
- **Obsidian vault** at `~/ObsidianVault/` with a `03-Resources/` directory

Dependencies (`qmd`, `marp-cli`) are installed automatically on first session start.

## Usage

### CLI

```bash
python -m pip install -e .
pyenv rehash

scridos wiki init my-topic
scridos wiki init my-topic --github
scridos wiki init 239-eagle --title "239 Eagle Dr" --root ./wiki
scridos wiki lint ./wiki/239-eagle
```

`scridos init` and `scridos lint` are also available as short aliases for the
same wiki operations.

For GitHub-first work, run `scridos wiki init <name> --github` from a repo root.
That creates `wiki/<name>/` inside the repo so the wiki can be reviewed, linked,
versioned, and pushed like any other project artifact. This is the preferred
mode when replacing Notion with GitHub as the operating system.

### Initialize a new wiki

```
/scridos:wiki init my-topic
```

Creates `~/ObsidianVault/03-Resources/my-topic/` with the full wiki structure: `raw/`, `wiki/`, `CLAUDE.md` schema, indexes, and git tracking.

### Ingest a source

```
/scridos:wiki ingest ~/ObsidianVault/03-Resources/my-topic/raw/article.md
/scridos:wiki ingest https://example.com/interesting-article
```

Saves the source to `raw/articles/`. Does not create wiki pages — use `compile` for that.

### Compile raw sources into wiki

```
/scridos:wiki compile
/scridos:wiki compile ~/ObsidianVault/03-Resources/my-topic/raw/articles/2026-04-05-article.md
```

Reads uncompiled raw sources, creates/updates wiki pages (source summary, concept pages, person pages), updates the index, and commits.

### Query the wiki

```
/scridos:wiki query "What is the relationship between X and Y?"
```

Searches the wiki (via qmd if available, otherwise index.md), reads relevant pages, and synthesizes an answer with `[[wikilink]]` citations. Offers to file the answer back into the wiki.

### Lint the wiki

```
/scridos:wiki lint
```

Checks for dead links, orphan pages, missing sections, contradictions, stale pages, and index drift. Auto-fixes what it can.

### Remove a wiki

```
/scridos:wiki remove my-topic
```

Deletes the wiki directory, removes the qmd collection, and commits the deletion.

## Wiki Structure

```
~/ObsidianVault/03-Resources/<wiki-name>/
├── raw/                  ← immutable source drops (never edited by LLM)
│   ├── articles/         ← text source documents
│   └── attachments/      ← images
├── wiki/                 ← LLM-owned pages
│   ├── index.md          ← catalog (read first)
│   ├── queries/          ← filed query answers
│   └── <concept>.md      ← entity/concept pages
├── outputs/
│   └── reports/          ← dated lint reports
├── CLAUDE.md             ← wiki schema and conventions
├── log.md                ← append-only operation log
├── .gitignore
└── qmd.yml               ← qmd collection config
```

## Obsidian Integration

- **Graph view**: wiki pages use `[[wikilinks]]` — Obsidian graph shows link topology for free
- **Dataview**: standardized frontmatter enables dynamic tables
- **Web Clipper**: save articles directly to `raw/`, then run ingest

## qmd Integration

qmd provides hybrid search (BM25 + vector) over the wiki. It's optional — the plugin falls back to reading `index.md` for small wikis. qmd is installed automatically via the SessionStart hook.

## Uninstall

```bash
claude plugin uninstall scridos
```

This removes the plugin and its dependency cache. Your wiki data in `~/ObsidianVault/` is preserved.

## License

MIT
