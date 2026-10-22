"""
LLM client wrapping OpenAI-compatible API (SiliconFlow / DeepSeek / Qwen).
Includes retry, usage tracking, and timing.
"""
import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger
import httpx
from openai import OpenAI, APIError, RateLimitError, APITimeoutError


@dataclass
class LLMUsage:
    """Token usage and timing for one LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0.0
    model: str = ""

    def __add__(self, other: "LLMUsage") -> "LLMUsage":
        return LLMUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            elapsed_seconds=self.elapsed_seconds + other.elapsed_seconds,
            model=self.model or other.model,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "model": self.model,
        }


@dataclass
class LLMResponse:
    """Wraps one LLM call's response."""
    content: str
    usage: LLMUsage
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)


class LLMClient:
    """OpenAI-compatible client. Defaults read from environment."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        self.base_url = base_url or os.getenv("SILICONFLOW_BASE_URL")
        self.model = model or os.getenv("SILICONFLOW_MODEL")

        if not (self.api_key and self.base_url and self.model):
            raise ValueError(
                "LLMClient needs api_key, base_url, model "
                "(via args or env vars SILICONFLOW_*)"
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            # Disable the SDK's hidden retries.  They can multiply a stalled
            # provider request beyond the experiment's configured deadline;
            # ``complete`` below owns retries and logs each one explicitly.
            max_retries=0,
            timeout=httpx.Timeout(
                timeout,
                connect=min(15.0, timeout),
                read=timeout,
                write=timeout,
                pool=min(15.0, timeout),
            ),
        )
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        # Track cumulative usage across calls
        self.cumulative_usage = LLMUsage(model=self.model)

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, str]] = None,
    ) -> LLMResponse:
        """
        Make one chat completion call with automatic retry.

        Args:
            messages: list of {"role": "...", "content": "..."}
            temperature: sampling temperature (default 0 for determinism)
            max_tokens: max completion tokens
            response_format: optional, e.g. {"type": "json_object"}
        """
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start = time.time()
                kwargs = dict(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                extra_body = {}
                siliconflow_thinking = os.getenv("SILICONFLOW_ENABLE_THINKING")
                if siliconflow_thinking:
                    normalized = siliconflow_thinking.strip().lower()
                    if normalized not in {"true", "false"}:
                        raise ValueError(
                            "SILICONFLOW_ENABLE_THINKING must be 'true' or 'false'"
                        )
                    extra_body["enable_thinking"] = normalized == "true"
                    thinking_budget = os.getenv("SILICONFLOW_THINKING_BUDGET")
                    if normalized == "true" and thinking_budget:
                        extra_body["thinking_budget"] = int(thinking_budget)
                thinking_type = os.getenv("DEEPSEEK_THINKING_TYPE")
                if thinking_type:
                    extra_body["thinking"] = {"type": thinking_type}
                reasoning_effort = os.getenv("DEEPSEEK_REASONING_EFFORT")
                if reasoning_effort:
                    kwargs["reasoning_effort"] = reasoning_effort
                if extra_body:
                    kwargs["extra_body"] = extra_body
                if response_format:
                    kwargs["response_format"] = response_format

                resp = self.client.chat.completions.create(**kwargs)
                elapsed = time.time() - start

                choice = resp.choices[0]
                message = choice.message
                content = message.content or ""
                reasoning_content = getattr(message, "reasoning_content", None) or ""
                usage = LLMUsage(
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                    total_tokens=resp.usage.total_tokens,
                    elapsed_seconds=elapsed,
                    model=self.model,
                )
                self.cumulative_usage = self.cumulative_usage + usage
                logger.debug(
                    f"LLM call OK: {usage.total_tokens} tokens, "
                    f"{usage.elapsed_seconds:.1f}s"
                )
                return LLMResponse(
                    content=content,
                    usage=usage,
                    raw={
                        "id": resp.id,
                        "model": resp.model,
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "reasoning_chars": len(reasoning_content),
                    },
                )

            except (RateLimitError, APITimeoutError, APIError) as e:
                last_err = e
                wait = self.retry_backoff ** attempt
                logger.warning(
                    f"LLM call attempt {attempt}/{self.max_retries} failed: "
                    f"{type(e).__name__}: {str(e)[:200]}. "
                    f"Retrying in {wait:.1f}s..."
                )
                time.sleep(wait)
            except Exception as e:
                last_err = e
                logger.error(f"Unexpected LLM error: {type(e).__name__}: {e}")
                raise

        raise RuntimeError(
            f"LLM call failed after {self.max_retries} retries: {last_err}"
        )

    def reset_usage(self):
        """Reset cumulative usage tracking."""
        self.cumulative_usage = LLMUsage(model=self.model)
