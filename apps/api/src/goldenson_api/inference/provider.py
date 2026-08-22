from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, object]] | None = None


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, object]


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


class LLMProviderTimeoutError(RuntimeError):
    pass


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse: ...


class _FunctionCall(BaseModel):
    name: str
    arguments: str = "{}"


class _ProviderToolCall(BaseModel):
    id: str
    function: _FunctionCall


class _ProviderMessage(BaseModel):
    content: str | None = None
    tool_calls: list[_ProviderToolCall] = Field(default_factory=list)


class _Choice(BaseModel):
    message: _ProviderMessage


class _CompletionResponse(BaseModel):
    choices: list[_Choice] = Field(min_length=1)


class OpenAICompatibleLocalProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "stream": False,
            "think": False,
            "reasoning_effort": "none",
        }
        if tools:
            payload["tools"] = list(tools)

        try:
            if self._client is not None:
                response = await self._client.post("/chat/completions", json=payload)
            else:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout_seconds,
                    trust_env=False,
                ) as client:
                    response = await client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMProviderTimeoutError("local model response timed out") from exc
        response.raise_for_status()
        completion = _CompletionResponse.model_validate(response.json())
        message = completion.choices[0].message
        calls: list[LLMToolCall] = []
        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments)
            if not isinstance(arguments, dict) or not all(
                isinstance(key, str) for key in arguments
            ):
                raise ValueError("provider returned invalid tool arguments")
            calls.append(
                LLMToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                )
            )
        return LLMResponse(content=message.content or "", tool_calls=calls)
