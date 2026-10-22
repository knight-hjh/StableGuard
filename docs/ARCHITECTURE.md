# Legacy execution architecture

The default entry point is `scripts/scan_c1c5.py`.

```text
dataset/<project>
  -> ProjectLoader / Slither
  -> run_detectors(contracts)
  -> candidate function and heuristic callee context
  -> subtype knowledge base + historical system prompt
  -> LLMClient.complete(..., max_tokens=900)
  -> response parsing
  -> per-project findings, all_verdicts, and usage
```

## Components

| Component | Implementation |
| --- | --- |
| Project parsing and fallback | `stableguard/core/project_loader.py` |
| Candidate discovery | `stableguard/stablecoin_specific/detectors.py` |
| Context selection | `_fn_text_map`, `_impl_map`, `_augment_code` in `scripts/scan_c1c5.py` |
| Prompt construction | `stableguard/stablecoin_specific/prompt.py` |
| Rule knowledge base | `config/knowledge_base/c1c5_kb.yaml` |
| Taxonomy definitions | `static_screening/lib/stablecoin_specific.py` |
| Provider communication | `stableguard/llm/client.py` |
| Response parsing | `stableguard/llm/response_parser.py` |

## Context limits

Function lookup uses file basenames and function names. Callee resolution uses
the first implementation found for a name, not a fully qualified call graph.
Augmentation searches up to depth 3 and selects signal-bearing functions within
a 5,800-character context budget. Prompt rendering separately slices code at
6,000 characters. Constructors, amount bounds, overload distinctions, or other
relevant functions can therefore be absent or incorrectly associated.

The project loader can fall back to parsing individual files. Parsing some files
does not prove complete project coverage. The historical fallback accumulates
contracts on the loader, while the scanner consumes the returned Slither object's
contracts; do not interpret fallback success as a complete union of every parsed
entry. This export preserves that implementation rather than silently fixing it.

## What this path does not implement

- It does not construct the newer operation-bound M1/M2 certificates.
- It does not provide a complete typed workflow graph or closed-world proof.
- It does not automatically send a positive result to an independent reviewer.
- It does not respond to a semantic context-gap report by re-running extraction.
- It does not establish source-version correctness of benchmark labels.

The separately included review and composition scripts are optional historical
utilities, not evidence that every old scan used those stages.
