"""Update the CSV and public directory through the official Devvit metadata reader."""

import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile

from directory_updater.auth import sync_auth
from directory_updater.dataset import read_csv, updated_dataset
from directory_updater.devvit import prepare, refresh
from directory_updater.render import render


ROOT = Path(__file__).resolve().parent


def write_directory(root, rows, fields=None):
    # Render and stage every output before replacing any existing directory file.
    readme, page = render(rows)
    outputs = {"README.md": readme, "docs/index.html": page}
    if fields is not None:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        outputs["subreddits.csv"] = buffer.getvalue()
    with tempfile.TemporaryDirectory(prefix="directory-", dir=root) as temporary:
        staged = Path(temporary)
        for name, content in outputs.items():
            source = staged / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="utf-8")
        for name in outputs:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (staged / name).replace(target)


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--render-only", action="store_true", help="Regenerate README and HTML without network access or CSV changes")
    mode.add_argument("--from-log", type=Path, metavar="FILE", help="Import a completed Devvit JSON log instead of requesting new metadata")
    mode.add_argument("--prepare", action="store_true", help="Validate CSV and generate the Devvit community list for builds/tests")
    mode.add_argument("--sync-auth", action="store_true", help="Copy the current Devvit CLI login to the ignored .env file")
    parser.add_argument("--dry-run", action="store_true", help="Retrieve/validate metadata without changing CSV, README or HTML")
    parser.add_argument("--timeout", type=int, default=1800, help="Maximum metadata wait in seconds (default: 1800)")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.dry_run and (args.render_only or args.prepare or args.sync_auth):
        parser.error("--dry-run requires a live refresh or --from-log")
    root = Path(root).resolve()
    if args.sync_auth:
        sync_auth(root)
        print("DEVVIT_AUTH_TOKEN saved in .env (permissions 600). Never commit this file.")
        return
    if args.prepare:
        print(f"Prepared {prepare(root)} communities from subreddits.csv.")
        return
    _, rows = read_csv(root / "subreddits.csv")
    if args.render_only:
        write_directory(root, rows)
        print("README.md and docs/index.html regenerated from the CSV.")
        return
    original = (root / "subreddits.csv").read_bytes()
    log = args.from_log or refresh(root, args.timeout)
    fields, rows, summary = updated_dataset(log, root / "subreddits.csv")
    # Validate rendering during previews too, before touching any public files.
    render(rows)
    if original != (root / "subreddits.csv").read_bytes():
        raise ValueError("CSV changed during the refresh; rerun using the current list.")
    if not args.dry_run:
        write_directory(root, rows, fields)
    summary["applied"] = not args.dry_run
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    report = json.dumps(summary, ensure_ascii=False, indent=2)
    (cache / "update-report.json").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, RuntimeError) as error:
        raise SystemExit(f"Error: {error}") from None
