"""Build and run the metadata reader on Reddit's official platform."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .auth import cli_environment
from .dataset import parse_timestamp, read_csv, read_run


def prepare(root):
    _, rows = read_csv(root / "subreddits.csv")
    source = root / "devvit/src/server/subreddits.ts"
    source.write_text(
        "// Generated from subreddits.csv by update.py --prepare.\n"
        "export const subredditNames = [\n"
        + "".join(f"  '{row['name']}',\n" for row in rows)
        + "] as const\n", encoding="utf-8",
    )
    return len(rows)


def refresh(root, timeout=1800):
    project = root / "devvit"
    environment = cli_environment(root)
    version = (project / ".nvmrc").read_text().strip().removeprefix("v")
    node_bin = Path.home() / ".nvm/versions/node" / f"v{version}" / "bin"
    if node_bin.is_dir():
        environment["PATH"] = str(node_bin) + os.pathsep + environment.get("PATH", "")
    node = shutil.which("node", path=environment.get("PATH"))
    npm = shutil.which("npm", path=environment.get("PATH"))
    cli = project / "node_modules/devvit/bin/devvit.js"
    if not node or not npm or not cli.exists():
        raise ValueError("Install Node 24 and run npm ci --prefix devvit first.")
    node_version = subprocess.check_output([node, "--version"], env=environment, text=True).strip()
    if int(node_version.removeprefix("v").split(".")[0]) < 24:
        raise ValueError(f"Node 24 or newer is required; found {node_version}.")
    count = prepare(root)
    config = json.loads((project / "devvit.json").read_text())
    subreddit, app = config["dev"]["subreddit"], config["name"]
    print(f"Reading metadata for {count} communities via {app}...", flush=True)
    subprocess.run([npm, "run", "build"], cwd=project, env=environment, check=True)
    subprocess.run([node, str(cli), "upload"], cwd=project, env=environment, check=True)
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    log_path = cache / "devvit.jsonl"
    started = datetime.now(timezone.utc)
    with log_path.open("w", encoding="utf-8") as handle:
        logs = subprocess.Popen(
            [node, str(cli), "logs", subreddit, app, "--since", "1m", "--json"],
            cwd=project, env=environment, stdout=handle,
        )
        try:
            subprocess.run([node, str(cli), "install", subreddit, app], cwd=project, env=environment, check=True)
            deadline = time.monotonic() + timeout
            last_notice = 0
            while time.monotonic() < deadline:
                if logs.poll() is not None:
                    raise RuntimeError("The Devvit log stream stopped; directory files were not changed.")
                try:
                    run, _, _ = read_run(log_path)
                    if parse_timestamp(run) >= started:
                        return log_path
                except ValueError:
                    pass  # Never import an incomplete run or a previous installation.
                if time.monotonic() - last_notice >= 30:
                    print("Waiting for community metadata...", flush=True)
                    last_notice = time.monotonic()
                time.sleep(2)
            raise RuntimeError("Timed out waiting for a complete run; directory files were not changed.")
        finally:
            logs.terminate()
            try:
                logs.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logs.kill()
                logs.wait()
