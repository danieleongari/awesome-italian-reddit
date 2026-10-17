"""Load the CLI credential without exposing it or unrelated .env keys."""

import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key


def sync_auth(root, token_path=None):
    source = Path(token_path) if token_path else Path.home() / ".devvit/token"
    if not source.is_file():
        raise ValueError("Run npx devvit login inside devvit/ first, then --sync-auth.")
    raw = source.read_text(encoding="utf-8").strip()
    stored = json.loads(raw)
    if not isinstance(stored, dict) or not isinstance(stored.get("token"), str):
        raise ValueError("The saved Devvit credential has an unexpected format.")
    env_path = Path(root) / ".env"
    if not env_path.exists():
        env_path.touch(mode=0o600)
    env_path.chmod(0o600)
    set_key(env_path, "DEVVIT_AUTH_TOKEN", json.dumps(stored, separators=(",", ":")), quote_mode="always")


def cli_environment(root):
    environment = os.environ.copy()
    # Explicit environment variables (GitHub Actions) take precedence over .env.
    token = environment.get("DEVVIT_AUTH_TOKEN") or dotenv_values(Path(root) / ".env").get("DEVVIT_AUTH_TOKEN")
    if not token:
        raise ValueError("Missing DEVVIT_AUTH_TOKEN: run python update.py --sync-auth or set the GitHub secret.")
    environment["DEVVIT_AUTH_TOKEN"] = token
    return environment
