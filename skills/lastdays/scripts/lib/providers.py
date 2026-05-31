"""Reasoning providers: Claude + OpenAI only. Default is 'local' (no LLM call).

On the Claude Code / Codex path the agent host IS the reasoning model, so the
engine calls no LLM (provider = 'local'). The OpenAI/Anthropic clients exist for
headless/cron use or an explicit second-opinion pass; OpenAI prefers the
subscription (Codex) token over an API key.
"""

from __future__ import annotations

import json

from . import env as env_mod
from . import http

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"  # subscription
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

OPENAI_MODEL = "gpt-5.1"
ANTHROPIC_MODEL = "claude-opus-4-8"


class OpenAIClient:
    name = "openai"

    def __init__(self, auth: dict):
        self.auth = auth

    def generate_text(self, prompt: str, model: str = OPENAI_MODEL) -> str:
        if self.auth.get("source") == "codex":
            payload = {
                "model": model,
                "stream": True,
                "store": False,
                "input": [
                    {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": prompt}]}
                ],
            }
            headers = {
                "Authorization": f"Bearer {self.auth['token']}",
                "chatgpt-account-id": self.auth.get("account_id") or "",
                "OpenAI-Beta": "responses=experimental",
                "originator": "codex_cli_rs",
                "Content-Type": "application/json",
            }
            raw = http.post_raw(CODEX_RESPONSES_URL, payload, headers=headers, timeout=90)
            return _extract_sse_text(raw)

        payload = {"model": model, "store": False, "input": prompt}
        resp = http.post(
            OPENAI_RESPONSES_URL,
            payload,
            headers={
                "Authorization": f"Bearer {self.auth['token']}",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        return _extract_openai_text(resp)


class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate_text(self, prompt: str, model: str = ANTHROPIC_MODEL) -> str:
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = http.post(
            ANTHROPIC_URL,
            payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        parts = resp.get("content") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


SYNTHESIS_PROMPT = (
    'You are a research analyst. The block below is engagement-ranked evidence from '
    'the last {days} days about "{topic}", gathered from public sources. Write a tight, '
    'grounded brief: a one-line headline, then 3-6 bullet findings (each citing the '
    'source and its real engagement numbers), then a one-line bottom line. Use ONLY '
    'what is in the evidence; never invent numbers. Match the language of the topic.\n\n'
    "{evidence}\n"
)


def synthesize(client, topic: str, days: int, evidence_md: str) -> str:
    """Generate a brief from the evidence using a reasoning client (headless/cron use)."""
    return client.generate_text(SYNTHESIS_PROMPT.format(days=days, topic=topic, evidence=evidence_md))


def resolve_runtime(config: dict, requested: str = "local"):
    """Return (provider_name, client_or_None).

    'local' (default) => engine calls no LLM; the agent host does the reasoning.
    'auto' => subscription-first: use whatever login/key is available (OpenAI first).
    Falls back to 'local' whenever the requested provider has no usable auth.
    """
    requested = (requested or "local").lower()
    if requested == "auto":
        auth = env_mod.openai_auth(config)
        if auth["source"] != "none":
            return "openai", OpenAIClient(auth)
        if config.get("ANTHROPIC_API_KEY"):
            return "anthropic", AnthropicClient(config["ANTHROPIC_API_KEY"])
        return "local", None
    if requested in ("local", "none", ""):
        return "local", None
    if requested == "openai":
        auth = env_mod.openai_auth(config)
        if auth["source"] == "none":
            return "local", None
        return "openai", OpenAIClient(auth)
    if requested == "anthropic":
        key = config.get("ANTHROPIC_API_KEY")
        if not key:
            return "local", None
        return "anthropic", AnthropicClient(key)
    return "local", None


def _extract_openai_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output") or payload.get("choices") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
        msg = item.get("message") or {}
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    return ""


def _extract_sse_text(raw: str) -> str:
    text = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            ev = json.loads(data)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "response.completed" and isinstance(ev.get("response"), dict):
            t = _extract_openai_text(ev["response"])
            if t:
                return t
        delta = ev.get("delta")
        if isinstance(delta, str):
            text += delta
    return text
