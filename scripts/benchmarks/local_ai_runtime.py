from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from goldenson_api.agent.tools import tool_definitions

SIMPLE_PROMPT = "Reply with exactly: GOLDENSON_OK"
TOOL_PROMPT = "Call list_pages exactly once. Do not explain."
AGENT_PROMPT = "What is my workspace about? Use the available tools when needed."
SYSTEM_PROMPT = (
    "You are GoldenSon's local workspace assistant. Use only the supplied retrieved "
    "context and validated tools. Never invent sources. Do not request secrets, paths, "
    "SQL, shell commands, environment variables, or arbitrary URLs. For a mutation, call "
    "the appropriate tool; the application will request approval. Keep answers concise.\n\n"
    "RETRIEVED WORKSPACE CONTEXT:\nNo relevant content found."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark a local OpenAI-compatible runtime"
    )
    parser.add_argument("--runtime", choices=("ollama", "llama.cpp"), required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-file", type=Path)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-size", type=int, default=8192)
    return parser.parse_args()


def runtime_payload(runtime: str) -> dict[str, object]:
    if runtime == "ollama":
        return {"think": False, "reasoning_effort": "none"}
    return {
        "reasoning_effort": "none",
        "chat_template_kwargs": {"enable_thinking": False},
    }


def process_rss_bytes(process_group: int) -> int:
    result = subprocess.run(
        ["ps", "-axo", "pgid=,rss="],
        check=True,
        capture_output=True,
        text=True,
    )
    rss_kib = 0
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) == 2 and int(columns[0]) == process_group:
            rss_kib += int(columns[1])
    return rss_kib * 1024


async def wait_until_ready(client: httpx.AsyncClient, health_path: str) -> None:
    deadline = time.perf_counter() + 300
    while time.perf_counter() < deadline:
        try:
            response = await client.get(health_path)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError("runtime did not become ready within 300 seconds")


def parse_sse_data(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    data = line[6:]
    if data == "[DONE]":
        return None
    parsed = json.loads(data)
    return parsed if isinstance(parsed, dict) else None


async def streaming_completion(
    client: httpx.AsyncClient,
    payload: dict[str, object],
) -> dict[str, object]:
    started = time.perf_counter()
    first_event_seconds: float | None = None
    first_content_seconds: float | None = None
    first_tool_seconds: float | None = None
    content = ""
    tool_names: list[str] = []
    reasoning_seen = False
    finish_reason: str | None = None

    async with client.stream("POST", "/chat/completions", json=payload) as response:
        if response.is_error:
            error_body = (await response.aread()).decode(errors="replace")
            return {
                "status_code": response.status_code,
                "error": error_body,
                "total_seconds": time.perf_counter() - started,
            }
        async for line in response.aiter_lines():
            event = parse_sse_data(line)
            if event is None:
                continue
            elapsed = time.perf_counter() - started
            if first_event_seconds is None:
                first_event_seconds = elapsed
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue
            chunk = delta.get("content")
            if isinstance(chunk, str) and chunk:
                content += chunk
                if first_content_seconds is None:
                    first_content_seconds = elapsed
            reasoning = delta.get("reasoning_content")
            reasoning_seen = (
                reasoning_seen or isinstance(reasoning, str) and bool(reasoning)
            )
            calls = delta.get("tool_calls")
            if isinstance(calls, list) and calls:
                if first_tool_seconds is None:
                    first_tool_seconds = elapsed
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if isinstance(name, str) and name and name not in tool_names:
                        tool_names.append(name)
            reason = choice.get("finish_reason")
            if isinstance(reason, str):
                finish_reason = reason

    return {
        "first_event_seconds": first_event_seconds,
        "ttft_seconds": first_content_seconds,
        "first_tool_seconds": first_tool_seconds,
        "total_seconds": time.perf_counter() - started,
        "content": content,
        "tool_names": tool_names,
        "reasoning_seen": reasoning_seen,
        "finish_reason": finish_reason,
    }


async def nonstream_tool_completion(
    client: httpx.AsyncClient,
    payload: dict[str, object],
) -> dict[str, object]:
    started = time.perf_counter()
    response = await client.post("/chat/completions", json={**payload, "stream": False})
    response.raise_for_status()
    body = response.json()
    message = body["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    parsed_calls = [
        {
            "name": call["function"]["name"],
            "arguments": json.loads(call["function"]["arguments"]),
        }
        for call in calls
    ]
    return {
        "total_seconds": time.perf_counter() - started,
        "tool_calls": parsed_calls,
        "reasoning_seen": bool(message.get("reasoning_content")),
    }


async def cancellation_probe(
    client: httpx.AsyncClient,
    base_payload: dict[str, object],
) -> dict[str, object]:
    payload = {
        **base_payload,
        "messages": [
            {
                "role": "user",
                "content": "Write the integers from 1 through 10000, one per line.",
            }
        ],
        "max_tokens": 4096,
        "stream": True,
    }
    started = time.perf_counter()
    first_token_seconds: float | None = None
    close_started: float | None = None
    async with client.stream("POST", "/chat/completions", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            event = parse_sse_data(line)
            if event is None:
                continue
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                first_token_seconds = time.perf_counter() - started
                close_started = time.perf_counter()
                break
    closed_seconds = time.perf_counter() - (close_started or time.perf_counter())

    probe_started = time.perf_counter()
    probe = await client.post(
        "/chat/completions",
        json={
            **base_payload,
            "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
            "max_tokens": 32,
            "stream": False,
        },
    )
    probe.raise_for_status()
    return {
        "first_token_seconds": first_token_seconds,
        "stream_close_seconds": closed_seconds,
        "post_cancel_probe_seconds": time.perf_counter() - probe_started,
        "probe_content": probe.json()["choices"][0]["message"].get("content", ""),
    }


def command_for(args: argparse.Namespace) -> tuple[list[str], dict[str, str], str]:
    environment = os.environ.copy()
    if args.runtime == "ollama":
        environment["OLLAMA_HOST"] = f"127.0.0.1:{args.port}"
        return [str(args.binary), "serve"], environment, "/api/version"
    if args.model_file is None:
        raise ValueError("--model-file is required for llama.cpp")
    command = [
        str(args.binary),
        "--model",
        str(args.model_file),
        "--alias",
        args.model,
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--ctx-size",
        str(args.context_size),
        "--parallel",
        "1",
        "--jinja",
        "--reasoning",
        "off",
        "--reasoning-budget",
        "0",
        "--no-ui",
        "--cors-origins",
        "localhost",
        "--no-cors-credentials",
        "--offline",
    ]
    return command, environment, "/health"


async def benchmark(args: argparse.Namespace) -> dict[str, object]:
    command, environment, health_path = command_for(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.output.with_suffix(".log")
    with log_path.open("wb") as log_file:
        started = time.perf_counter()
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            origin = f"http://127.0.0.1:{args.port}"
            async with httpx.AsyncClient(
                base_url=origin, timeout=300, trust_env=False
            ) as health:
                await wait_until_ready(health, health_path)
            async with httpx.AsyncClient(
                base_url=f"{origin}/v1", timeout=300, trust_env=False
            ) as client:
                startup_seconds = time.perf_counter() - started
                memory_at_ready = process_rss_bytes(process.pid)
                base_payload: dict[str, object] = {
                    "model": args.model,
                    "temperature": 0,
                    **runtime_payload(args.runtime),
                }
                simple = await streaming_completion(
                    client,
                    {
                        **base_payload,
                        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
                        "max_tokens": 32,
                        "stream": True,
                    },
                )
                memory_after_load = process_rss_bytes(process.pid)
                single_tool = [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_pages",
                            "description": "List workspace pages.",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]
                tool_stream = await streaming_completion(
                    client,
                    {
                        **base_payload,
                        "messages": [{"role": "user", "content": TOOL_PROMPT}],
                        "tools": single_tool,
                        "max_tokens": 128,
                        "stream": True,
                    },
                )
                tool_nonstream = await nonstream_tool_completion(
                    client,
                    {
                        **base_payload,
                        "messages": [{"role": "user", "content": TOOL_PROMPT}],
                        "tools": single_tool,
                        "max_tokens": 128,
                    },
                )
                agent = await streaming_completion(
                    client,
                    {
                        **base_payload,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": AGENT_PROMPT},
                        ],
                        "tools": tool_definitions(),
                        "max_tokens": 256,
                        "stream": True,
                    },
                )
                cancellation = await cancellation_probe(client, base_payload)
                memory_after_tests = process_rss_bytes(process.pid)
                return {
                    "runtime": args.runtime,
                    "model": args.model,
                    "model_file": str(args.model_file) if args.model_file else None,
                    "command": command,
                    "startup_seconds": startup_seconds,
                    "memory_bytes": {
                        "ready": memory_at_ready,
                        "after_model_load": memory_after_load,
                        "after_tests": memory_after_tests,
                    },
                    "simple_stream": simple,
                    "tool_stream": tool_stream,
                    "tool_nonstream": tool_nonstream,
                    "agent_first_turn": agent,
                    "cancellation": cancellation,
                    "log_path": str(log_path),
                }
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


def main() -> None:
    args = parse_args()
    result = asyncio.run(benchmark(args))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
