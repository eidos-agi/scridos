from pathlib import Path
import tempfile
import unittest

from scridos_cli import task_doctor_findings, write_file


def task(root: Path, name: str, body: str, *, source: str = "wiki/source.md", status: str = "ready") -> None:
    write_file(
        root / "ops" / "tasks" / f"{name}.md",
        f"""---
id: {name}
title: Test Task
type: task
status: {status}
source: {source}
---
# Test Task

{body}
""",
    )


class TaskDoctorTests(unittest.TestCase):
    def test_passes_clean_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_file(root / "wiki" / "source.md", "# Source\n")
            task(root, "clean", "## Outcome\n\nDone.\n\n## Next Action\n\nAct.\n")
            self.assertEqual(task_doctor_findings(root), [])

    def test_flags_literal_newlines_duplicate_headings_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task(
                root,
                "bad",
                "# Test Task\n\n## Outcome\\nBroken import.\n",
                source="wiki/missing.md",
            )
            messages = [finding[2] for finding in task_doctor_findings(root)]
            self.assertTrue(any("literal escaped newlines" in message for message in messages))
            self.assertTrue(any("duplicate markdown headings" in message for message in messages))
            self.assertTrue(any("source path does not exist" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
