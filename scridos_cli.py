#!/usr/bin/env python3
"""Small CLI wrapper for scridos wiki scaffolding and deterministic linting."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


TODAY = date.today().isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "wiki"


def wiki_root_from_args(args: argparse.Namespace) -> Path:
    if args.github:
        return (Path.cwd() / "wiki" / slugify(args.name)).resolve()
    base = Path(args.root).expanduser().resolve()
    return base if args.here else base / slugify(args.name)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_wiki(args: argparse.Namespace) -> int:
    root = wiki_root_from_args(args)
    name = slugify(args.name)
    title = args.title or args.name.replace("-", " ").title()

    if root.exists() and any(root.iterdir()):
        print(f"Wiki already exists and is not empty: {root}", file=sys.stderr)
        return 1

    for rel in [
        "raw/articles",
        "raw/attachments",
        "wiki/queries",
        "outputs/reports",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)

    write_file(root / "CLAUDE.md", claude_template(name, title))
    write_file(root / "wiki/index.md", index_template(name, title))
    write_file(root / "log.md", log_template(name, title))
    write_file(root / ".gitignore", ".DS_Store\n*.sqlite\n*.sqlite-wal\n*.sqlite-shm\n")
    write_file(root / "qmd.yml", f"collections:\n  {name}:\n    path: ./wiki\n    pattern: \"**/*.md\"\n")

    if args.commit:
        git_commit(root, f"init: {name} wiki")

    print(f"Initialized scridos wiki: {root}")
    print(f"Next: add raw sources under {root / 'raw/articles'}")
    return 0


def lint_wiki(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    wiki_dir = root / "wiki" if (root / "wiki").is_dir() else root
    script = Path(__file__).resolve().parent / "scripts" / "lint-wiki.py"
    if script.exists():
        return subprocess.call([sys.executable, str(script), str(wiki_dir)])
    print(f"Lint script missing: {script}", file=sys.stderr)
    return 1


def git_commit(root: Path, message: str) -> None:
    repo = root
    while repo != repo.parent and not (repo / ".git").exists():
        repo = repo.parent
    if not (repo / ".git").exists():
        return
    rel = os.path.relpath(root, repo)
    subprocess.call(["git", "-C", str(repo), "add", rel])
    subprocess.call(["git", "-C", str(repo), "commit", "-m", message])


def claude_template(name: str, title: str) -> str:
    return f"""# {title} Wiki Schema

This is a scridos wiki. It is a persistent, compounding markdown knowledge base
for the `{name}` domain.

## Directory Layout
- raw/              -- immutable source drops. Never edit files here.
- raw/articles/     -- text source documents, exports, transcripts, and notes.
- raw/attachments/  -- images and binary attachments.
- wiki/             -- LLM-owned pages.
- wiki/index.md     -- catalog. Read this first before opening any other page.
- wiki/queries/     -- filed query answers. Promote to wiki/ when durable.
- outputs/reports/  -- dated lint reports and other artifacts.
- log.md            -- append-only operation log. Never edit existing entries.

## Entity Templates

### concept.md
---
date: YYYY-MM-DD
tags: [domain]
type: concept
status: active
---
# Concept Name
One-paragraph summary.

## Details

## See Also
- [[related-concept]]

## Counter-Arguments and Gaps

### person.md
---
date: YYYY-MM-DD
tags: [domain, person]
type: person
status: active
---
# Person Name
Role / affiliation.

## Key Contributions

## See Also
- [[related-concept]]

### source-summary.md
---
date: YYYY-MM-DD
tags: [domain]
type: source-summary
source-url: path-or-url
---
# Source Title
One-paragraph summary.

## Key Points

## Entities Mentioned
- [[person-or-concept]]

## Naming Conventions
- Filenames are lowercase-kebab-case.md.
- Internal links use `[[wikilinks]]`.
- Raw sources are immutable after ingest.
- Every durable page should appear in `wiki/index.md`.

## Log Format
Append to log.md after every operation:

  ## [YYYY-MM-DD] operation | title
  One-line description.
"""


def index_template(name: str, title: str) -> str:
    return f"""---
date: {TODAY}
tags: [{name}]
type: index
status: active
---
# {title} Wiki

## Start Here
- [[overview]] -- operating map for this wiki ({TODAY})

## Sources

## People

## Tasks and Workflows

## Money and Payables
"""


def log_template(name: str, title: str) -> str:
    return f"""# {title} Wiki Log

## [{TODAY}] init | {name}
Initialized scridos wiki scaffold.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scridos")
    sub = parser.add_subparsers(dest="command", required=True)

    add_commands(sub)

    wiki = sub.add_parser("wiki", help="wiki operations")
    wiki_sub = wiki.add_subparsers(dest="wiki_command", required=True)
    add_commands(wiki_sub)

    return parser


def add_commands(sub: argparse._SubParsersAction) -> None:
    init = sub.add_parser("init", help="initialize a wiki")
    init.add_argument("name")
    init.add_argument("--title")
    init.add_argument("--root", default="~/ObsidianVault/03-Resources")
    init.add_argument("--here", action="store_true", help="initialize directly in --root")
    init.add_argument("--github", action="store_true", help="initialize under ./wiki/<name> for a GitHub repo")
    init.add_argument("--commit", action="store_true", help="commit scaffold in containing git repo")
    init.set_defaults(func=init_wiki)

    lint = sub.add_parser("lint", help="lint a wiki directory")
    lint.add_argument("path", nargs="?", default=".")
    lint.set_defaults(func=lint_wiki)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
