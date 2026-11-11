from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import BadRequestError, OpenAI

from .agent import MalformedToolCallError
from .config import PROVIDERS


@dataclass
class ChatResponse:
    message: Any
    prompt_tokens: int
    completion_tokens: int


class LLMClient:
    def __init__(self, client: OpenAI, model: str, provider: str):
        self.client = client
        self.model = model
        self.provider = provider

    @classmethod
    def from_env(cls) -> LLMClient:
        provider_name = os.environ.get("LLM_PROVIDER", "groq").lower()
        if provider_name not in PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider_name!r}"
            )
        provider = PROVIDERS[provider_name]
        api_key = "ollama"
        if provider.api_key_env:
            api_key = os.environ.get(provider.api_key_env, "")
            if not api_key:
                raise RuntimeError(
                    f"{provider.api_key_env} is not set. Add it to .env (see .env.example)."
                )
        model = os.environ.get("LLM_MODEL", provider.default_model)
        # The SDK retries 429s with backoff, which matters on free-tier rate limits.
        client = OpenAI(api_key=api_key, base_url=provider.base_url, max_retries=6, timeout=120)
        return cls(client, model, provider_name)

    def chat(self, messages: list[dict], tools: list[dict] | None) -> ChatResponse:
        kwargs: dict[str, Any] = {"tools": tools, "tool_choice": "auto"} if tools else {}
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0, **kwargs
            )
        except BadRequestError as exc:
            # Groq returns 400 when the model emits a tool call that doesn't match the schema.
            if "tool call validation failed" in str(exc).lower():
                raise MalformedToolCallError(str(exc)) from exc
            raise
        usage = response.usage
        return ChatResponse(
            message=response.choices[0].message,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
