#!/usr/bin/env python3
"""CLI for scridos repo-native wikis and text-backed project work."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


TODAY = date.today().isoformat()
KINDS = ("project", "milestone", "task")
KANBAN_COLUMNS = ("backlog", "ready", "doing", "blocked", "done")
OPEN_STATUSES = {"open", "backlog", "ready", "doing"}
VALID_TASK_STATUSES = {*KANBAN_COLUMNS, "open", "closed"}
TASK_REQUIRED_FIELDS = ("id", "title", "type", "status")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def wiki_root_from_args(args: argparse.Namespace) -> Path:
    if args.github:
        return (Path.cwd() / "wiki" / slugify(args.name)).resolve()
    base = Path(args.root).expanduser().resolve()
    return base if args.here else base / slugify(args.name)


def init_wiki(args: argparse.Namespace) -> int:
    root = wiki_root_from_args(args)
    name = slugify(args.name)
    title = args.title or args.name.replace("-", " ").title()

    if root.exists() and any(root.iterdir()):
        print(f"Wiki already exists and is not empty: {root}", file=sys.stderr)
        return 1

    for rel in [
        "ops/projects",
        "ops/milestones",
        "ops/tasks",
        "raw/articles",
        "raw/attachments",
        "wiki/queries",
        "outputs/reports",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)

    write_file(root / "ops/README.md", ops_readme_template(title))
    write_file(root / "CLAUDE.md", claude_template(name, title))
    write_file(root / "wiki/index.md", index_template(name, title))
    write_file(root / "log.md", log_template(name, title))
    write_file(root / ".gitignore", ".DS_Store\n*.sqlite\n*.sqlite-wal\n*.sqlite-shm\n")
    write_file(root / "qmd.yml", f"collections:\n  {name}:\n    path: ./wiki\n    pattern: \"**/*.md\"\n")

    if args.commit:
        git_commit(root, f"init: {name} wiki")

    print(f"Initialized scridos wiki: {root}")
    print("Next: scridos task add \"First task\"")
    return 0


def lint_wiki(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    wiki_dir = root / "wiki" if (root / "wiki").is_dir() else root
    script = Path(__file__).resolve().parent / "scripts" / "lint-wiki.py"
    if script.exists():
        return subprocess.call([sys.executable, str(script), str(wiki_dir)])
    print(f"Lint script missing: {script}", file=sys.stderr)
    return 1


def ops_create(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    record_id = unique_id(root, args.kind, args.id or slugify(args.title))
    fields = build_fields(args.kind, args, record_id)
    body = args.body or getattr(args, "description", "") or ""
    write_record(root, args.kind, fields, body)
    append_log(root, f"{args.kind} create", record_id, f"Created {args.kind}: {args.title}.")
    print(record_path(root, args.kind, record_id))
    return 0


def ops_list(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    records = filtered_records(root, args.kind, args)
    if getattr(args, "next_only", False):
        records = [r for r in records if r["fields"].get("status", "open") in OPEN_STATUSES]
        records = sort_tasks(records)[:1]
    elif args.kind == "task":
        records = sort_tasks(records)
    print_records(args.kind, records)
    return 0


def filtered_records(root: Path, kind: str, args: argparse.Namespace) -> list[dict]:
    records = read_records(root, kind)
    for key in ["project", "milestone", "status", "owner", "priority"]:
        value = getattr(args, key, None)
        if value:
            records = [r for r in records if r["fields"].get(key) == value]
    if kind == "task" and not getattr(args, "all", False) and not getattr(args, "status", None):
        records = [r for r in records if r["fields"].get("status", "open") not in {"done", "closed"}]
    return records


def print_records(kind: str, records: list[dict]) -> None:
    if not records:
        print(f"No {kind}s found.")
        return
    for record in records:
        fields = record["fields"]
        parts = [fields["id"], fields["title"]]
        for key in ["status", "priority", "due", "project", "milestone", "owner"]:
            if fields.get(key):
                parts.append(f"{key}={fields[key]}")
        print(" | ".join(parts))


def sort_tasks(records: list[dict]) -> list[dict]:
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    status_rank = {"doing": 0, "ready": 1, "open": 1, "backlog": 2, "blocked": 8, "done": 9}

    def key(record: dict) -> tuple:
        fields = record["fields"]
        return (
            status_rank.get(fields.get("status", "").lower(), 5),
            priority_rank.get(fields.get("priority", "").lower(), 9),
            fields.get("due") or "9999-99-99",
            fields.get("title", ""),
        )

    return sorted(records, key=key)


def ops_show(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    path = record_path(root, args.kind, args.id)
    if not path.exists():
        print(f"{args.kind} not found: {args.id}", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def ops_update(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    path = record_path(root, args.kind, args.id)
    if not path.exists():
        print(f"{args.kind} not found: {args.id}", file=sys.stderr)
        return 1
    fields, body = parse_record(path)
    for field in editable_fields(args.kind):
        value = getattr(args, field.replace("-", "_"), None)
        if value is not None:
            fields[field.replace("-", "_")] = value
    if args.body is not None:
        body = args.body
    fields["updated"] = TODAY
    write_record(root, args.kind, fields, body)
    append_log(root, f"{args.kind} update", args.id, f"Updated {args.kind}: {fields.get('title', args.id)}.")
    print(path)
    return 0


def ops_delete(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    path = record_path(root, args.kind, args.id)
    if not path.exists():
        print(f"{args.kind} not found: {args.id}", file=sys.stderr)
        return 1
    path.unlink()
    append_log(root, f"{args.kind} delete", args.id, f"Deleted {args.kind}: {args.id}.")
    print(f"Deleted {path}")
    return 0


def task_done(args: argparse.Namespace) -> int:
    args.kind = "task"
    args.status = "done"
    args.body = None
    args.title = None
    args.source = None
    args.project = None
    args.milestone = None
    args.owner = None
    args.priority = None
    args.due = None
    args.next_action = None
    return ops_update(args)


def task_move(args: argparse.Namespace) -> int:
    args.kind = "task"
    args.body = None
    args.title = None
    args.source = None
    args.project = None
    args.milestone = None
    args.owner = None
    args.priority = None
    args.due = None
    args.next_action = None
    return ops_update(args)


def task_next(args: argparse.Namespace) -> int:
    args.kind = "task"
    args.next_only = True
    if not getattr(args, "all", False) and not getattr(args, "status", None):
        args.status = None
    return ops_list(args)


def work_list(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    print("Projects")
    print_records("project", filtered_records(root, "project", args))
    print("\nMilestones")
    print_records("milestone", filtered_records(root, "milestone", args))
    print("\nTasks")
    print_records("task", sort_tasks(filtered_records(root, "task", args)))
    return 0


def board_view(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    records = sort_tasks(filtered_records(root, "task", args))
    by_status = {column: [] for column in KANBAN_COLUMNS}
    by_status["other"] = []
    for record in records:
        status = record["fields"].get("status", "open")
        if status == "open":
            status = "ready"
        by_status.setdefault(status, by_status["other"]).append(record)

    for column in [*KANBAN_COLUMNS, "other"]:
        items = by_status.get(column, [])
        if not items and not args.all:
            continue
        print(column.upper())
        if not items:
            print("  empty")
            continue
        for record in items:
            fields = record["fields"]
            meta = []
            for key in ["priority", "due", "owner"]:
                if fields.get(key):
                    meta.append(f"{key}={fields[key]}")
            suffix = f" ({', '.join(meta)})" if meta else ""
            print(f"  - {fields['id']}: {fields['title']}{suffix}")
        print()
    return 0


def task_doctor(args: argparse.Namespace) -> int:
    root = resolve_wiki_root(args.wiki)
    findings = task_doctor_findings(root)
    if not findings:
        print(f"task doctor: PASS ({record_dir(root, 'task')})")
        return 0

    errors = [item for item in findings if item[0] == "ERROR"]
    warnings = [item for item in findings if item[0] == "WARN"]
    print(f"task doctor: {len(errors)} error(s), {len(warnings)} warning(s)")
    for severity, path, message in findings:
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        print(f"{severity} {rel}: {message}")
    return 0 if args.warn_only or not errors else 1


def task_doctor_findings(root: Path) -> list[tuple[str, Path, str]]:
    findings: list[tuple[str, Path, str]] = []
    tasks = read_records(root, "task")
    ids: dict[str, Path] = {}
    for record in tasks:
        path = record["path"]
        fields = record["fields"]
        body = record["body"]
        text = path.read_text(encoding="utf-8", errors="replace")
        task_id = fields.get("id", path.stem)

        if task_id in ids:
            findings.append(("ERROR", path, f"duplicate task id also used by {ids[task_id]}"))
        ids[task_id] = path

        for field in TASK_REQUIRED_FIELDS:
            if not fields.get(field):
                findings.append(("ERROR", path, f"missing required frontmatter field `{field}`"))
        if fields.get("type") and fields["type"] != "task":
            findings.append(("ERROR", path, f"type should be `task`, got `{fields['type']}`"))
        status = fields.get("status", "")
        if status and status not in VALID_TASK_STATUSES:
            findings.append(("ERROR", path, f"unknown status `{status}`"))
        if task_id and slugify(task_id) != path.stem:
            findings.append(("WARN", path, f"id `{task_id}` does not match filename `{path.stem}`"))

        source = fields.get("source", "")
        if source and not source_exists(root, source):
            findings.append(("ERROR", path, f"source path does not exist: {source}"))
        if not source:
            findings.append(("WARN", path, "missing source field"))

        if "\\n" in body:
            findings.append(("ERROR", path, "body contains literal escaped newlines (`\\n`)"))
        if re.search(r"(?<![$\d]),\d{3}\b", body) or re.search(r"\band\s*,\d{3}\b", body):
            findings.append(("WARN", path, "body may contain a broken imported money amount"))

        headings = re.findall(r"(?m)^#\s+(.+)$", body)
        if not headings:
            findings.append(("WARN", path, "missing H1 heading in body"))
        elif fields.get("title") and headings[0].strip() != fields["title"].strip():
            findings.append(("WARN", path, "first H1 does not match title frontmatter"))
        if len(headings) != len(set(headings)):
            findings.append(("ERROR", path, "duplicate markdown headings detected"))

        for section in ("## Outcome", "## Next Action"):
            if section not in body:
                findings.append(("WARN", path, f"missing `{section}` section"))

        if status == "done":
            if "## Evidence" not in body and "## Current Evidence" not in body and "## Companion Docs" not in body and not source:
                findings.append(("ERROR", path, "done task lacks evidence/companion docs/source"))
            if source and not source_exists(root, source):
                findings.append(("ERROR", path, "done task source is missing"))

    return findings


def source_exists(root: Path, source: str) -> bool:
    if not source or source.startswith(("http://", "https://")):
        return bool(source)
    raw = Path(source).expanduser()
    if raw.is_absolute():
        return raw.exists()
    candidates = [root / raw]
    repo = containing_git_root(root)
    if repo:
        candidates.append(repo / raw)
    if len(root.parents) >= 2:
        candidates.append(root.parents[1] / raw)
    return any(path.exists() for path in candidates)


def containing_git_root(path: Path) -> Path | None:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return current if (current / ".git").exists() else None


def resolve_wiki_root(path: str) -> Path:
    current = Path(path).expanduser().resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / "CLAUDE.md").is_file() and (current / "wiki").is_dir():
            return current
        candidates = sorted((current / "wiki").glob("*/CLAUDE.md")) if (current / "wiki").is_dir() else []
        if len(candidates) == 1:
            return candidates[0].parent
        if current == current.parent:
            break
        current = current.parent
    print(f"No scridos wiki root found from {path}", file=sys.stderr)
    raise SystemExit(1)


def record_dir(root: Path, kind: str) -> Path:
    return root / "ops" / f"{kind}s"


def record_path(root: Path, kind: str, record_id: str) -> Path:
    return record_dir(root, kind) / f"{slugify(record_id)}.md"


def unique_id(root: Path, kind: str, base: str) -> str:
    candidate = slugify(base)
    counter = 2
    while record_path(root, kind, candidate).exists():
        candidate = f"{slugify(base)}-{counter}"
        counter += 1
    return candidate


def read_records(root: Path, kind: str) -> list[dict]:
    records = []
    for path in sorted(record_dir(root, kind).glob("*.md")):
        fields, body = parse_record(path)
        records.append({"path": path, "fields": fields, "body": body})
    return records


def parse_record(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {"id": path.stem, "title": path.stem}, text
    _, frontmatter, body = text.split("---", 2)
    fields = {}
    for line in frontmatter.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    fields.setdefault("id", path.stem)
    fields.setdefault("title", fields["id"])
    return fields, body.lstrip()


def build_fields(kind: str, args: argparse.Namespace, record_id: str) -> dict:
    fields = {
        "id": record_id,
        "title": args.title,
        "type": kind,
        "status": args.status,
        "created": TODAY,
        "updated": TODAY,
    }
    for field in editable_fields(kind):
        value = getattr(args, field.replace("-", "_"), None)
        if value is not None:
            fields[field.replace("-", "_")] = value
    return fields


def write_record(root: Path, kind: str, fields: dict, body: str) -> None:
    lines = ["---"]
    for key in ["id", "title", "type", "status", "project", "milestone", "owner", "priority", "due", "source", "created", "updated"]:
        if fields.get(key):
            lines.append(f"{key}: {fields[key]}")
    for key in sorted(k for k in fields if k not in {line.split(':', 1)[0] for line in lines if ':' in line}):
        if fields.get(key):
            lines.append(f"{key}: {fields[key]}")
    lines.append("---")
    title = fields.get("title", fields["id"])
    content = "\n".join(lines) + f"\n# {title}\n\n"
    if body.strip():
        content += body.strip() + "\n"
    else:
        content += "## Outcome\n\n## Next Action\n\n## Source Links\n"
    write_file(record_path(root, kind, fields["id"]), content)


def editable_fields(kind: str) -> list[str]:
    common = ["title", "status", "source"]
    if kind == "project":
        return common + ["owner"]
    if kind == "milestone":
        return common + ["project", "due"]
    return common + ["project", "milestone", "owner", "priority", "due", "next_action"]


def append_log(root: Path, operation: str, title: str, line: str) -> None:
    log = root / "log.md"
    prior = log.read_text(encoding="utf-8") if log.exists() else "# Wiki Log\n"
    write_file(log, f"{prior.rstrip()}\n\n## [{TODAY}] {operation} | {title}\n{line}\n")


def git_commit(root: Path, message: str) -> None:
    repo = root
    while repo != repo.parent and not (repo / ".git").exists():
        repo = repo.parent
    if not (repo / ".git").exists():
        return
    rel = os.path.relpath(root, repo)
    subprocess.call(["git", "-C", str(repo), "add", rel])
    subprocess.call(["git", "-C", str(repo), "commit", "-m", message])


def ops_readme_template(title: str) -> str:
    return f"""# {title} Operations

Scridos stores project work as plain text markdown files:

- `projects/` -- durable work containers.
- `milestones/` -- dated outcomes inside projects.
- `tasks/` -- accountable next actions.

These files are meant to be reviewed, diffed, linked, and committed.
"""


def claude_template(name: str, title: str) -> str:
    return f"""# {title} Wiki Schema

This is a scridos wiki. It combines durable project knowledge with text-backed
project, milestone, and task records for the `{name}` domain.

## Directory Layout
- raw/              -- immutable source drops. Never edit files here.
- raw/articles/     -- text source documents, exports, transcripts, and notes.
- raw/attachments/  -- images and binary attachments.
- ops/              -- markdown project, milestone, and task records.
- ops/projects/     -- one markdown file per project.
- ops/milestones/   -- one markdown file per milestone.
- ops/tasks/        -- one markdown file per task.
- wiki/             -- LLM-owned pages.
- wiki/index.md     -- catalog. Read this first before opening any other page.
- wiki/queries/     -- filed query answers. Promote to wiki/ when durable.
- outputs/reports/  -- dated lint reports and other artifacts.
- log.md            -- append-only operation log. Never edit existing entries.

## Operating Model

The wiki explains durable understanding. The ops files track execution.

- A project describes a durable body of work.
- A milestone describes a dated outcome within a project.
- A task describes one accountable next action.

Use text files, not external issue trackers, as the source of truth.

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

### task.md
---
id: task-id
title: Task Title
type: task
status: open
project: project-id
milestone: milestone-id
owner: person
priority: high
due: YYYY-MM-DD
source: wiki/page.md
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
# Task Title

## Outcome

## Next Action

## Source Links

## Naming Conventions
- Filenames are lowercase-kebab-case.md.
- Internal wiki links use `[[wikilinks]]`.
- Ops records are markdown text files with simple frontmatter.
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
    parser = argparse.ArgumentParser(
        prog="scridos",
        description="Repo-native wiki and work management.",
    )
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

    for kind in KINDS:
        add_ops_commands(sub, kind)

    next_cmd = sub.add_parser("next", help="show the next open task")
    add_task_filter_args(next_cmd)
    next_cmd.set_defaults(func=task_next)

    board = sub.add_parser("board", help="show tasks as a kanban board")
    add_task_filter_args(board)
    board.set_defaults(func=board_view)

    work = sub.add_parser("work", help="project work commands")
    work_actions = work.add_subparsers(dest="action", required=True)
    work_list_cmd = work_actions.add_parser("list", help="list active projects, milestones, and tasks")
    add_task_filter_args(work_list_cmd)
    work_list_cmd.set_defaults(func=work_list)
    work_next_cmd = work_actions.add_parser("next", help="show the next open task")
    add_task_filter_args(work_next_cmd)
    work_next_cmd.set_defaults(func=task_next)
    work_board_cmd = work_actions.add_parser("board", help="show tasks as a kanban board")
    add_task_filter_args(work_board_cmd)
    work_board_cmd.set_defaults(func=board_view)


def add_ops_commands(sub: argparse._SubParsersAction, kind: str) -> None:
    parent = sub.add_parser(kind, help=f"{kind} commands")
    actions = parent.add_subparsers(dest="action", required=True)

    for action in ["create", "add"]:
        create = actions.add_parser(action, help=f"add a {kind}")
        add_common_ops_args(create)
        create.add_argument("title")
        create.add_argument("--id")
        create.add_argument("--status", default="backlog" if kind == "task" else "open")
        create.add_argument("--body")
        add_edit_args(create, kind)
        create.set_defaults(func=ops_create, kind=kind)

    list_cmd = actions.add_parser("list", help=f"list {kind}s")
    add_common_ops_args(list_cmd)
    list_cmd.add_argument("--project")
    list_cmd.add_argument("--milestone")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--owner")
    list_cmd.add_argument("--priority")
    list_cmd.add_argument("--all", action="store_true", help="include done/closed tasks")
    list_cmd.set_defaults(func=ops_list, kind=kind)

    show = actions.add_parser("show", help=f"show a {kind}")
    add_common_ops_args(show)
    show.add_argument("id")
    show.set_defaults(func=ops_show, kind=kind)

    for action in ["update", "edit"]:
        update = actions.add_parser(action, help=f"edit a {kind}")
        add_common_ops_args(update)
        update.add_argument("id")
        update.add_argument("--status")
        update.add_argument("--body")
        add_edit_args(update, kind, include_title=True)
        update.set_defaults(func=ops_update, kind=kind)

    for action in ["delete", "rm"]:
        delete = actions.add_parser(action, help=f"delete a {kind}")
        add_common_ops_args(delete)
        delete.add_argument("id")
        delete.set_defaults(func=ops_delete, kind=kind)

    if kind == "task":
        doctor = actions.add_parser("doctor", help="validate canonical task files")
        add_common_ops_args(doctor)
        doctor.add_argument("--warn-only", action="store_true", help="exit 0 even when errors are found")
        doctor.set_defaults(func=task_doctor)

        move = actions.add_parser("move", help="move a task to a kanban column")
        add_common_ops_args(move)
        move.add_argument("id")
        move.add_argument("status", choices=KANBAN_COLUMNS)
        move.set_defaults(func=task_move)

        start = actions.add_parser("start", help="move a task to doing")
        add_common_ops_args(start)
        start.add_argument("id")
        start.set_defaults(func=task_move, status="doing")

        block = actions.add_parser("block", help="move a task to blocked")
        add_common_ops_args(block)
        block.add_argument("id")
        block.set_defaults(func=task_move, status="blocked")

        done = actions.add_parser("done", help="mark a task done")
        add_common_ops_args(done)
        done.add_argument("id")
        done.set_defaults(func=task_done)

        next_cmd = actions.add_parser("next", help="show the next open task")
        add_task_filter_args(next_cmd)
        next_cmd.set_defaults(func=task_next)

        board = actions.add_parser("board", help="show tasks as a kanban board")
        add_task_filter_args(board)
        board.set_defaults(func=board_view)


def add_common_ops_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wiki", default=".", help="path inside or at a scridos wiki")


def add_task_filter_args(parser: argparse.ArgumentParser) -> None:
    add_common_ops_args(parser)
    parser.add_argument("--project")
    parser.add_argument("--milestone")
    parser.add_argument("--status")
    parser.add_argument("--owner")
    parser.add_argument("--priority")
    parser.add_argument("--all", action="store_true", help="include done/closed tasks")


def add_edit_args(parser: argparse.ArgumentParser, kind: str, include_title: bool = False) -> None:
    if include_title:
        parser.add_argument("--title")
    parser.add_argument("--source")
    if kind in {"project", "task"}:
        parser.add_argument("--owner")
    if kind in {"milestone", "task"}:
        parser.add_argument("--project")
        parser.add_argument("--due")
    if kind == "task":
        parser.add_argument("--milestone")
        parser.add_argument("--priority")
        parser.add_argument("--next-action", dest="next_action")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
