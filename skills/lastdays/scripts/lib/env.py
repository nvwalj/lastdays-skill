"""Config loading + OpenAI subscription (Codex) auth detection.

Precedence (low -> high): macOS keychain < ~/.config/lastdays/.env < project
.env < process environment. No key is required on the default path - the agent
host is the LLM. OpenAI auth is detected best-effort, preferring the ChatGPT/
Codex subscription token over an API key.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "lastdays"
KEYCHAIN_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN")


def _parse_env_file(path: Path) -> dict:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _load_keychain() -> dict:
    if sys.platform != "darwin":
        return {}
    out: dict[str, str] = {}
    user = os.environ.get("USER", "")
    for key in KEYCHAIN_KEYS:
        try:
            r = subprocess.run(
                ["security", "find-generic-password", "-a", user, "-s", f"lastdays-{key}", "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and r.stdout.strip():
            out[key] = r.stdout.strip()
    return out


def get_config() -> dict:
    cfg: dict[str, str] = {}
    cfg.update(_load_keychain())
    cfg.update(_parse_env_file(CONFIG_DIR / ".env"))
    cfg.update(_parse_env_file(Path.cwd() / ".env"))
    cfg.update(os.environ)
    return cfg


def _decode_jwt_account_id(token: str):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, IndexError, json.JSONDecodeError):
        return None
    auth = data.get("https://api.openai.com/auth") or {}
    return auth.get("chatgpt_account_id") or data.get("chatgpt_account_id")


def load_codex_auth():
    """Return (access_token, account_id) from ~/.codex/auth.json, else (None, None)."""
    path = Path.home() / ".codex" / "auth.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, None
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else data
    token = tokens.get("access_token") or tokens.get("id_token")
    if not token:
        return None, None
    return token, _decode_jwt_account_id(token)


def openai_auth(config: dict) -> dict:
    """Resolve OpenAI auth, subscription-first.

    The ChatGPT/Codex subscription token wins by default so the normal path spends
    no money; the paid OPENAI_API_KEY is the fallback. Set LASTDAYS_OPENAI_PREFER_KEY=1
    to force the API key instead. Returns {"source": "codex"|"api_key"|"none", ...}.
    """
    prefer_key = str(config.get("LASTDAYS_OPENAI_PREFER_KEY", "")).strip().lower() in ("1", "true", "yes")
    if not prefer_key:
        token, account_id = load_codex_auth()
        if token:
            return {"source": "codex", "token": token, "account_id": account_id}
    if config.get("OPENAI_API_KEY"):
        return {"source": "api_key", "token": config["OPENAI_API_KEY"], "account_id": None}
    if prefer_key:
        token, account_id = load_codex_auth()
        if token:
            return {"source": "codex", "token": token, "account_id": account_id}
    return {"source": "none", "token": None, "account_id": None}
