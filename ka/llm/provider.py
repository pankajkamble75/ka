from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from ka import config


class LLMProviderError(RuntimeError):
    pass


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    model: str | None = None
    cost_usd: float = 0.0

    def add(self, other: "LLMUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls
        self.cost_usd += other.cost_usd
        self.model = other.model or self.model

    def as_dict(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens, "calls": self.calls}


# USD per 1M tokens (input, output). Enough for the research-run cost field (§16); not a billing system.
_PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    if not model:
        return 0.0
    for key, (pin, pout) in _PRICES.items():
        if model.startswith(key):
            return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000
    return 0.0


class LLMProvider(Protocol):
    name: str
    last_usage: LLMUsage

    def complete(self, prompt: str, *, system: str | None = None, model: str | None = None,
                 max_tokens: int | None = None, temperature: float = 0.2) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        import anthropic  # local import: the stub path must not need the SDK

        self._client = anthropic.Anthropic(api_key=api_key or config.get("ANTHROPIC_API_KEY") or None,
                                           max_retries=0, timeout=config.get("KA_LLM_TIMEOUT"))
        self.default_model = default_model or config.get("KA_LLM_MODEL")
        self.last_usage = LLMUsage()

    def complete(self, prompt, *, system=None, model=None, max_tokens=None, temperature=0.2):
        import anthropic

        model = (model or self.default_model).removeprefix("anthropic:")
        max_tokens = max_tokens or config.get("KA_LLM_MAX_TOKENS")
        delay = 1.0
        for attempt in range(5):
            try:
                kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, temperature=temperature,
                                              messages=[{"role": "user", "content": prompt}])
                if system:
                    kwargs["system"] = system
                resp = self._client.messages.create(**kwargs)
                text = "".join(getattr(b, "text", "") for b in resp.content)
                u = resp.usage
                self.last_usage = LLMUsage(u.input_tokens, u.output_tokens, 1, model,
                                           estimate_cost(model, u.input_tokens, u.output_tokens))
                return text
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
                if attempt == 4:
                    raise LLMProviderError(str(e)) from e
                time.sleep(delay)
                delay *= 2
            except anthropic.APIStatusError as e:
                raise LLMProviderError(str(e)) from e
        raise LLMProviderError("unreachable")  # pragma: no cover


@dataclass
class StubLLMProvider:
    """Deterministic provider for tests. `responses` maps a marker found in the prompt to a reply;
    `default_response` answers anything else. Records every prompt in `calls`."""
    responses: dict[str, str] = field(default_factory=dict)
    default_response: str = "[]"
    name: str = "stub"
    calls: list[str] = field(default_factory=list)
    last_usage: LLMUsage = field(default_factory=LLMUsage)

    def complete(self, prompt, *, system=None, model=None, max_tokens=None, temperature=0.2):
        self.calls.append(prompt)
        reply = self.default_response
        for marker, text in self.responses.items():
            if marker in prompt:
                reply = text
                break
        self.last_usage = LLMUsage(len(prompt) // 4, len(reply) // 4, 1, model or "stub")
        return reply


def select_provider() -> LLMProvider:
    choice = (config.get("KA_LLM_PROVIDER") or "").lower()
    if choice == "stub":
        return StubLLMProvider()
    if choice == "anthropic" or (not choice and config.get("ANTHROPIC_API_KEY")):
        return AnthropicProvider()
    if "pytest" in sys.modules or not choice:
        return StubLLMProvider()
    raise LLMProviderError(f"unknown KA_LLM_PROVIDER {choice!r}")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def complete_json(provider: LLMProvider, prompt: str, *, system: str | None = None, default: Any = None) -> Any:
    """Ask for JSON and parse it leniently (fenced or bare). Returns `default` on garbage rather than
    raising: a failed recommendation is a missing recommendation, not a failed governance step."""
    text = provider.complete(prompt, system=system)
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    body = body.strip()
    for candidate in (body, body[body.find("["):body.rfind("]") + 1], body[body.find("{"):body.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return default
