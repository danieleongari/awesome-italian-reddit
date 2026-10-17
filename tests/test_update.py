import contextlib
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dotenv import dotenv_values

from directory_updater.auth import cli_environment, sync_auth
from directory_updater.dataset import read_csv
from directory_updater.devvit import prepare
from update import main


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "subreddits.csv"
        fields = ["name", "tag", "language", "subs", "description", "reason", "created_utc", "subs.1"]
        with self.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows([
                {"name": "italy", "tag": "<tag>", "language": "it", "subs": "10.0", "description": "old", "created_utc": "2008-07-25", "subs.1": "7.0"},
                {"name": "New_Community", "tag": "manual"},
                {"name": "unavailable", "subs": "5", "description": "preserve", "reason": "private"},
            ])
        (self.root / "docs").mkdir()
        (self.root / "README.md").write_text("old readme")
        (self.root / "docs/index.html").write_text("old html")
        self.log = self.root / "run.jsonl"
        self.make_log()

    def make_log(self, complete=True, include_new=True, bad_count=False, all_failed=False):
        run = "2026-10-17T13:00:00Z"
        events = [("SUBREDDIT_REFRESH_START", {"run": run, "total": 3})]
        for name in ["italy", "New_Community", "unavailable"]:
            if not include_new and name == "New_Community":
                continue
            if name == "unavailable" or all_failed:
                events.append(("SUBREDDIT_METADATA_ERROR", {"run": run, "name": name, "error": "missing metadata"}))
            else:
                events.append(("SUBREDDIT_METADATA", {
                    "run": run, "name": name, "subs": -1 if bad_count else 123,
                    "description": "Test | <script> & Italia", "updated_utc": run,
                    "created_utc": "2020-02-03T00:00:00Z",
                }))
        if complete:
            events.append(("SUBREDDIT_REFRESH_DONE", {"run": run, "total": 3}))
        self.log.write_text("\n".join(json.dumps({"message": prefix + " " + json.dumps(event)}) for prefix, event in events))

    def run_main(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            main(args, root=self.root)

    def snapshot(self):
        return {name: (self.root / name).read_bytes() for name in ["subreddits.csv", "README.md", "docs/index.html"]}

    def test_manual_additions_drive_generated_list_and_all_outputs(self):
        source = self.root / "devvit/src/server"
        source.mkdir(parents=True)
        prepare(self.root)
        self.assertIn("'New_Community'", (source / "subreddits.ts").read_text())
        self.run_main(["--from-log", str(self.log)])
        _, rows = read_csv(self.csv)
        self.assertEqual([row["subs"] for row in rows], ["123", "123", "5"])
        self.assertEqual(rows[0]["subs.1"], "7.0")
        self.assertEqual(rows[0]["created_utc"], "2008-07-25")
        self.assertEqual(rows[0]["language"], "it")
        self.assertEqual(rows[1]["created_utc"], "2020-02-03 00:00:00")
        self.assertEqual(rows[1]["tag"], "manual")
        self.assertEqual(rows[2]["description"], "preserve")
        readme = (self.root / "README.md").read_text()
        self.assertIn("r/New_Community", readme)
        self.assertIn("&#124;", readme)
        self.assertNotIn("r/unavailable", readme)
        page = (self.root / "docs/index.html").read_text()
        self.assertIn("&lt;tag&gt;", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("Test | <script>", page)
        report = json.loads((self.root / ".cache/update-report.json").read_text())
        self.assertEqual(report["failed_preserved"], {"unavailable": "missing metadata"})

    def test_partial_bad_or_all_failed_run_preserves_every_output(self):
        original = self.snapshot()
        for options in [{"complete": False}, {"include_new": False}, {"bad_count": True}, {"all_failed": True}]:
            with self.subTest(options=options):
                self.make_log(**options)
                with self.assertRaises(ValueError):
                    self.run_main(["--from-log", str(self.log)])
                self.assertEqual(self.snapshot(), original)

    def test_preview_preserves_directory_files(self):
        original = self.snapshot()
        self.run_main(["--from-log", str(self.log), "--dry-run"])
        self.assertEqual(self.snapshot(), original)

    def test_offline_render_never_calls_refresh_and_preserves_csv(self):
        original = self.csv.read_bytes()
        with patch("update.refresh") as live:
            self.run_main(["--render-only"])
        live.assert_not_called()
        self.assertEqual(self.csv.read_bytes(), original)
        self.assertIn("r/italy", (self.root / "README.md").read_text())
        self.assertNotIn("r/New_Community", (self.root / "README.md").read_text())

    def test_duplicate_names_rejected_before_live_refresh(self):
        self.csv.write_text("name\nitaly\nITALY\n")
        with patch("update.refresh") as live:
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.run_main([])
        live.assert_not_called()

    def test_changed_csv_during_live_refresh_is_not_overwritten(self):
        def change_csv(*args):
            self.csv.write_text(self.csv.read_text().replace("old", "edited while waiting"))
            return self.log
        with patch("update.refresh", side_effect=change_csv):
            with self.assertRaisesRegex(ValueError, "CSV changed"):
                self.run_main([])
        self.assertIn("edited while waiting", self.csv.read_text())
        self.assertEqual((self.root / "README.md").read_text(), "old readme")

    def test_render_validation_failure_preserves_all_outputs(self):
        self.csv.write_text(self.csv.read_text().replace("2008-07-25", "bad-date"))
        original = self.snapshot()
        with self.assertRaises(ValueError):
            self.run_main(["--from-log", str(self.log)])
        self.assertEqual(self.snapshot(), original)


class AuthTests(unittest.TestCase):
    def test_sync_preserves_other_keys_and_limits_file_access(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            credential = root / "token"
            value = {"token": "encoded-test-credential", "copyPaste": True}
            credential.write_text(json.dumps(value))
            (root / ".env").write_text("OPENAI_API_KEY=unrelated-test-value\n")
            sync_auth(root, credential)
            values = dotenv_values(root / ".env")
            self.assertEqual(json.loads(values["DEVVIT_AUTH_TOKEN"]), value)
            self.assertEqual(values["OPENAI_API_KEY"], "unrelated-test-value")
            self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
            with patch.dict(os.environ, {}, clear=True):
                env = cli_environment(root)
            self.assertEqual(env["DEVVIT_AUTH_TOKEN"], values["DEVVIT_AUTH_TOKEN"])
            self.assertNotIn("OPENAI_API_KEY", env)
            with patch.dict(os.environ, {"DEVVIT_AUTH_TOKEN": "ci-secret"}, clear=True):
                self.assertEqual(cli_environment(root)["DEVVIT_AUTH_TOKEN"], "ci-secret")

    def test_missing_credentials_give_instructions(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "sync-auth"):
                cli_environment(Path(folder))


if __name__ == "__main__":
    unittest.main()
