import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from directory_updater.dataset import updated_dataset
from update import write_directory


def import_run(log_path, csv_path, apply=False):
    fields, rows, summary = updated_dataset(log_path, csv_path)
    if apply:
        write_directory(csv_path.parent, rows, fields)
    return {**summary, "applied": apply}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.csv = Path(self.directory.name) / "subreddits.csv"
        self.log = Path(self.directory.name) / "run.log"
        with self.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["name", "subs", "description", "created_utc", "reason", "tag"])
            writer.writeheader()
            writer.writerows([
                {"name": "italy", "subs": "10", "description": "Old", "created_utc": "2008-07-25 00:00:00", "tag": "country"},
                {"name": "Italia", "subs": "20", "description": "Keep", "reason": "private", "tag": "country"},
            ])
        self.original = self.csv.read_bytes()

    def write_log(self, records, errors=(), done=True):
        run = "2026-10-17T00:00:00Z"
        messages = ["SUBREDDIT_REFRESH_START " + json.dumps({"run": run, "total": 2})]
        for record in records:
            messages.append("SUBREDDIT_METADATA " + json.dumps({"run": run, "updated_utc": run, **record}))
        for error in errors:
            messages.append("SUBREDDIT_METADATA_ERROR " + json.dumps({"run": run, **error}))
        if done:
            messages.append("SUBREDDIT_REFRESH_DONE " + json.dumps({"run": run, "total": 2}))
        self.log.write_text("\n".join(json.dumps({"message": message}) for message in messages))

    def test_missing_description_preserves_text_but_updates_count(self):
        self.write_log([
            {"name": "italy", "subs": 123, "description": "New"},
            {"name": "Italia", "subs": 456, "description": None},
        ])
        preview = import_run(self.log, self.csv)
        self.assertFalse(preview["applied"])
        self.assertEqual(self.csv.read_bytes(), self.original)
        import_run(self.log, self.csv, apply=True)
        rows = list(csv.DictReader(io.StringIO(self.csv.read_text())))
        self.assertEqual(rows[0]["subs"], "123")
        self.assertEqual(rows[1]["subs"], "456")
        self.assertEqual(rows[1]["description"], "Keep")
        self.assertEqual(rows[1]["reason"], "private")
        self.assertEqual(rows[0]["created_utc"], "2008-07-25 00:00:00")

    def test_failure_keeps_old_values(self):
        self.write_log([{"name": "italy", "subs": 123, "description": "New"}], [{"name": "Italia", "error": "blocked"}])
        result = import_run(self.log, self.csv, apply=True)
        self.assertEqual(result["failed_preserved"], {"Italia": "blocked"})
        rows = list(csv.DictReader(io.StringIO(self.csv.read_text())))
        self.assertEqual(rows[1]["subs"], "20")

    def test_incomplete_or_invalid_run_never_writes(self):
        self.write_log([{"name": "italy", "subs": 123, "description": "New"}], done=False)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            import_run(self.log, self.csv, apply=True)
        self.assertEqual(self.csv.read_bytes(), self.original)
        self.write_log([
            {"name": "italy", "subs": 123, "description": "New"},
            {"name": "Italia", "subs": None, "description": "New"},
        ])
        with self.assertRaisesRegex(ValueError, "Invalid subscriber"):
            import_run(self.log, self.csv, apply=True)
        self.assertEqual(self.csv.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
