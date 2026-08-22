# Local AI runtime benchmark

Date: 2026-08-22

## Scope

This spike compares Ollama and llama.cpp without changing GoldenSon's production runtime.
Both runtimes used the exact same Qwen 3 14B Q4_K_M GGUF weights.

Priority order: reliability, tool calling, streaming, cancellation, reasoning control,
startup time, memory, then raw speed.

## Environment

- MacBook Air, Apple M3, arm64
- macOS 26.5.2
- 24 GiB unified memory
- Ollama 0.32.15
- llama.cpp build 10566, commit `bb4caa754`, version `0.2.0-dev`
- Context size: 8192 for llama.cpp
- One llama.cpp inference slot

Model:

- Ollama ID: `qwen3:14b`
- Family: Qwen 3, 14.8B parameters
- Quantization: Q4_K_M
- GGUF SHA-256: `a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e`

llama.cpp artifact:

- `llama-b10566-bin-macos-arm64.tar.gz`
- SHA-256: `533f546dab2ce2f8e29ce3070f26acc55acc59528e177f2cd0d52b7f69b44f50`
- Downloaded from the official `ggml-org/llama.cpp` GitHub release
- The executable is ad-hoc/linker signed, with no Apple Team ID

## Configuration

Both runtimes received deterministic temperature-zero requests. Non-thinking mode was
explicit rather than inferred:

- Ollama: `think: false` and `reasoning_effort: none`
- llama.cpp: `--reasoning off`, `--reasoning-budget 0`,
  `reasoning_effort: none`, and `enable_thinking: false`

llama.cpp bound only to `127.0.0.1`. The UI was disabled, CORS was restricted to
localhost without credentials, offline mode was enabled, and no built-in tools, MCP,
media path, router, or model-download feature was enabled.

## Results

| Measurement | Ollama | llama.cpp |
| --- | ---: | ---: |
| Runtime ready | 0.116 s | 1.356 s |
| Simple first token | 1.697 s | 0.361 s |
| Simple total | 2.252 s | 0.919 s |
| Streamed tool call available | 3.076 s | 2.550 s |
| Streamed tool request total | 3.290 s | 3.335 s |
| Non-streamed tool request total | 1.800 s | 1.797 s |
| Cancel stream close | 0.0017 s | 0.0015 s |
| Post-cancel probe | 0.896 s | 0.883 s |
| Resident memory after load | 9.41 GiB | 9.99 GiB |
| Resident memory after tests | 9.59 GiB | 10.03 GiB |

Runtime-ready measurements are not identical lifecycle events. Ollama reports ready before
loading a model, while llama.cpp reports ready after loading its configured model. The first
Ollama request therefore includes model-load work. Memory is summed RSS for each launched
process group and may double-count shared mappings, so it is useful only as a local comparison.

## Behavioral findings

### Reliability and tools

Both runtimes returned exactly `GOLDENSON_OK` for the deterministic prompt. Both produced a
valid OpenAI-compatible `list_pages` call with `{}` arguments in streamed and non-streamed
requests.

Ollama accepted GoldenSon's full production tool schema set. For the realistic first-turn
request, it completed in 13.134 seconds but answered with a request for permission instead of
calling a READ tool. This is a model behavior failure, not a protocol failure.

llama.cpp rejected GoldenSon's full tool schema set with HTTP 400 before inference:

```text
Failed to initialize samplers: failed to parse grammar
```

Its generated grammar expands the `create_file.content` schema limit of 100,000 characters
and exceeds llama.cpp's grammar repetition safety bound. The benchmark did not weaken the
production schema to make the request pass. Consequently, llama.cpp cannot currently run a
real GoldenSon agent turn with the existing approved tools.

### Streaming and cancellation

Both OpenAI-compatible endpoints streamed content and tool-call deltas correctly. Closing a
stream after the first token returned immediately, and both runtimes accepted a follow-up
request in under one second.

GoldenSon's current `LLMProvider` is non-streaming and checks agent cancellation only between
provider calls. These runtime results do not make cancellation responsive through the current
production provider contract.

### Reasoning control

Neither runtime emitted reasoning content in any completed non-thinking probe. Ollama's
explicit request-level control and llama.cpp's server/request controls both worked reliably in
this run. The earlier 91-second Ollama result used default thinking and is not comparable to
these non-thinking measurements.

## Reproduction

The harness is [scripts/benchmarks/local_ai_runtime.py](../scripts/benchmarks/local_ai_runtime.py).
Run it from `apps/api` with `PYTHONPATH=src uv run python`, passing the runtime binary, model,
an unused loopback port, and an output JSON path. For llama.cpp, also pass the pinned GGUF with
`--model-file`.

The harness starts an isolated runtime process, waits for health, runs all probes, records raw
JSON and a runtime log, and terminates the process group. It does not install a runtime or model
and does not modify GoldenSon configuration.

## Recommendation

**A. Keep Ollama as the primary runtime.**

llama.cpp provides materially better simple TTFT on this machine and excellent explicit
reasoning control, streaming, and cancellation. It does not, however, meet the higher-priority
reliability requirement because it rejects GoldenSon's actual tool schemas. Ollama remains the
only tested runtime that accepts the complete agent contract unchanged.

Do not migrate or add a second production runtime based on this spike. Reconsider llama.cpp
after its grammar compiler accepts GoldenSon's schemas, or after a separately reviewed schema
design can preserve the same validation and security guarantees without the problematic bounds.