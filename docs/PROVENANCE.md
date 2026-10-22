# Export provenance

Prepared on 2026-10-18 from the existing legacy C1-C5 modules.

The following copied files have the same content hashes as the historical
Reachable-65 context-recovery method pins:

- `scripts/scan_c1c5.py`
- `stableguard/stablecoin_specific/prompt.py`
- `stableguard/stablecoin_specific/detectors.py`
- `config/knowledge_base/c1c5_kb.yaml`
- `scripts/eval_stablecoin_specific.py`

`provenance/HISTORICAL_METHOD_PINS.json` records those original identities.
`provenance/EXPORT_MANIFEST.json` inventories all copied source files and their
origins. `provenance/SHA256SUMS` covers copied files and the generated metadata
listed there; it does not cover subsequently added documentation, packaging
files, or the new offline evaluation wrapper.

The evaluation-only JSON was reserialized without changing its fields. It is not
claimed to retain the original JSON byte layout. The original CSV bytes are retained.

Support modules such as the generic LLM client are copied from the existing
workspace, but are not all covered by the five historical method pins. In
particular, the generic client is not the frozen DeepSeek experiment executor.

New files consist of repository documentation, packaging/configuration templates,
the offline Reachable-65 wrapper, and provenance records. No copied source module
was edited. Original workspace files and experiment results remain untouched.

No API calls, installations, compilation, tests, or post-copy validation were
performed as part of this organization task. Source identity information is not
a claim that the exported environment has been executed successfully.
