"""
Heuristic Shadow Agent - Multi-Provider LLM Client
Implements a fallback chain: DeepSeek (primary) -> Qwen (secondary) -> Hunyuan (tertiary)
Each provider has its own API format adapter.
"""

import logging
import time
import json
from typing import Optional, Generator

from openai import OpenAI
import httpx

from config import Config

logger = logging.getLogger(__name__)


class LLMResponse:
    """Unified response wrapper across providers."""

    def __init__(self, content: str, provider: str, model: str, tokens: int = 0):
        self.content = content
        self.provider = provider
        self.model = model
        self.tokens = tokens

    def __repr__(self):
        return f"LLMResponse(provider={self.provider}, len={len(self.content)})"


class LLMClient:
    """
    Multi-provider LLM client with automatic fallback.
    Provider order: DeepSeek -> Qwen -> Hunyuan
    """

    PROVIDERS = ["deepseek", "qwen", "hunyuan"]

    # Provider configurations
    PROVIDER_CONFIG = {
        "deepseek": {
            "model": "deepseek-chat",
            "base_url": Config.DEEPSEEK_BASE_URL,
            "api_keys": [
                Config.DEEPSEEK_API_KEY,
                Config.DEEPSEEK_ALT_API_KEY,
            ],
            "timeout": 60,
        },
        "qwen": {
            "model": "qwen-plus",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_keys": [Config.QWEN_API_KEY],
            "timeout": 45,
        },
        "hunyuan": {
            "model": "hunyuan-lite",
            "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
            "api_keys": [Config.HUNYUAN_API_KEY],
            "timeout": 45,
        },
    }

    def __init__(self):
        self._clients = {}
        self._provider_stats = {p: {"success": 0, "fail": 0, "total_tokens": 0} for p in self.PROVIDERS}
        self._init_clients()

    def _init_clients(self) -> None:
        """Pre-initialize OpenAI-compatible clients for each provider."""
        for provider in self.PROVIDERS:
            cfg = self.PROVIDER_CONFIG[provider]
            api_key = next((k for k in cfg["api_keys"] if k and k.strip()), "")
            if not api_key:
                logger.warning(f"Provider '{provider}' has no API key configured.")
                continue

            try:
                self._clients[provider] = OpenAI(
                    api_key=api_key,
                    base_url=cfg["base_url"],
                    timeout=cfg["timeout"],
                    max_retries=2,
                )
                logger.info(f"LLM client '{provider}' initialized ({cfg['model']}).")
            except Exception as e:
                logger.warning(f"Failed to init '{provider}' client: {e}")

    # ------------------------------------------------------------------
    # Chat completion with fallback
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Send a chat completion request with automatic provider fallback.
        Returns the first successful response.
        """
        errors = []

        for provider in self.PROVIDERS:
            if provider not in self._clients:
                continue

            try:
                cfg = self.PROVIDER_CONFIG[provider]
                client = self._clients[provider]

                # Build full message list
                full_messages = []
                if system_prompt:
                    full_messages.append({"role": "system", "content": system_prompt})
                full_messages.extend(messages)

                logger.debug(f"Calling {provider} ({cfg['model']}) with {len(full_messages)} messages...")
                start = time.time()

                response = client.chat.completions.create(
                    model=cfg["model"],
                    messages=full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                elapsed = time.time() - start
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0

                self._provider_stats[provider]["success"] += 1
                self._provider_stats[provider]["total_tokens"] += tokens

                logger.info(
                    f"LLM success: {provider}/{cfg['model']} "
                    f"({elapsed:.1f}s, {tokens} tokens)"
                )

                return LLMResponse(
                    content=content,
                    provider=provider,
                    model=cfg["model"],
                    tokens=tokens,
                )

            except Exception as e:
                err_msg = f"{provider}: {type(e).__name__}: {e}"
                errors.append(err_msg)
                self._provider_stats[provider]["fail"] += 1
                logger.warning(f"LLM provider '{provider}' failed: {e}")
                continue

        # All providers exhausted
        raise RuntimeError(
            f"All LLM providers failed. Errors: {'; '.join(errors)}"
        )

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: list,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Streaming version with fallback (falls back to non-streaming for simplicity)."""
        try:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )
            yield response.content
        except RuntimeError:
            yield "[ERROR] All LLM providers failed."

    # ------------------------------------------------------------------
    # Health & stats
    # ------------------------------------------------------------------

    def get_available_providers(self) -> list:
        """List currently available (configured) providers."""
        return list(self._clients.keys())

    def get_stats(self) -> dict:
        """Get provider usage statistics."""
        return {
            "providers": dict(self._provider_stats),
            "available": self.get_available_providers(),
            "total_requests": sum(s["success"] + s["fail"] for s in self._provider_stats.values()),
        }

    def health_check(self) -> dict:
        """Quick health check for each provider."""
        results = {}
        for provider in self.PROVIDERS:
            if provider not in self._clients:
                results[provider] = {"status": "unconfigured"}
                continue
            try:
                self.chat(
                    messages=[{"role": "user", "content": "Reply with just 'OK'."}],
                    temperature=0,
                    max_tokens=5,
                )
                results[provider] = {"status": "healthy"}
            except Exception as e:
                results[provider] = {"status": "unhealthy", "error": str(e)[:200]}

        return results
