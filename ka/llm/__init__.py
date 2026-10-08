"""LLM access for Knowledge Acquisition. Same shape as enterprise-os's knowledge_worker.llm: a provider
protocol, an Anthropic provider, a stub for tests, and a selector that picks by setting / key / pytest.

The LLM may recommend; it never establishes enterprise truth (§33). Every call here produces candidates,
explanations or suggestions that a governance decision still has to accept.
"""
from ka.llm.provider import (
    LLMProvider,
    LLMProviderError,
    LLMUsage,
    StubLLMProvider,
    complete_json,
    select_provider,
)

__all__ = ["LLMProvider", "LLMProviderError", "LLMUsage", "StubLLMProvider", "complete_json", "select_provider"]
