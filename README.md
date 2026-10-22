# StableGuard (Legacy)

**Static analysis and LLM-assisted recognition of backing-related defect mechanisms in stablecoin contracts.**

This repository contains the legacy C1-C5 implementation associated with the
Reachable-65 experiments. It combines Solidity candidate discovery, heuristic
cross-function context augmentation, and subtype-specific LLM analysis. The
original detector, prompt, rule knowledge base, and historical matcher are
preserved. This is not the newer M0-M3 implementation.

**Release status:** repository packaging and documentation are prepared.
Installation and execution of this export have not yet been validated. No
inference API was called during packaging.

## Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Outputs](#outputs)
- [Benchmark evaluation](#benchmark-evaluation)
- [Additional utilities](#additional-utilities)
- [Repository structure](#repository-structure)
- [Reproducibility and limitations](#reproducibility-and-limitations)
- [Documentation](#documentation)
- [Contributing, security, and licensing](#contributing-security-and-licensing)

## Overview

The legacy taxonomy contains five macro categories and 19 named subtypes
(`S01`-`S19`). These describe the analysis scope, not a guarantee of complete
detection coverage.

| Category | Focus |
| --- | --- |
| C1: Backing Mis-Valuation | Incorrect valuation or conversion of backing assets |
| C2: Unbacked Issuance | Issuance inconsistent with the backing available or received |
| C3: Supply-Backing Ledger Desynchronization | Inconsistent supply, liability, or backing accounting |
| C4: Liquidation and Solvency Failure | Incorrect liquidation or loss-settlement behavior |
| C5: Par-Redemption Violation | Violations of the intended issuance/redemption value relationship |

```text
Solidity project
  -> Slither-based candidate discovery
  -> candidate function + selected callee bodies
  -> subtype-specific rules and LLM judgment
  -> structured alerts, candidate outcomes, and usage records
```

### What does a positive result mean?

The historical prompt uses **fix-agnostic mechanism recognition**. A result with
`defect_present=true` may identify a mechanism location even when protection is
present or the code is patched. It is not independent confirmation of an active
vulnerability. The default scan does not run an adversarial-review/context-repair
loop; source review must be distinguished from the initial model judgment.

The rule file's strict-evaluation header does not override the actual historical
system prompt. This difference is documented rather than silently changed.

## Requirements

- Python 3.10 or newer.
- Linux or a compatible POSIX environment; the scanner uses alarm signals.
- Python dependencies listed in `requirements.txt`.
- The target project's exact Solidity compiler, build configuration, and dependencies.
- An authorized OpenAI-compatible API endpoint and its exact model identifier.

Project loading supports Foundry, Hardhat, and plain Solidity inputs through
Slither. Whether a particular checkout compiles depends on its own build setup;
installing the Python requirements does not install every project's toolchain.

## Quick start

Run all commands from this repository root.

### 1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

An editable installation is optional: `python -m pip install -e .`.
Keep the checkout in place; standalone wheel distribution is not supported by
the historical checkout-relative rule loader.

### 2. Configure the provider

Edit the local `.env` file:

```dotenv
SILICONFLOW_API_KEY=YOUR_API_KEY
SILICONFLOW_BASE_URL=https://YOUR_PROVIDER/v1
SILICONFLOW_MODEL=EXACT_PROVIDER_MODEL_ID
JOBS=1
RUN_CROSS=0
```

The `SILICONFLOW_*` names are retained for compatibility; the configured URL
determines the backend. The distributed `.env.example` contains placeholders,
not working credentials. Use only thinking parameters supported by your provider;
see [configuration](docs/CONFIGURATION.md).

### 3. Prepare a project

Place an authorized checkout under `dataset/ExampleProtocol/`, retaining its
original source layout, dependency locks, and build settings. Install the exact
compiler and project dependencies separately. Complete protocol repositories and
audit PDFs are not bundled with this code release.

### 4. Run the scanner

**The following command sends source excerpts and rules to the configured API
and can incur charges. There is no global token-budget limit in this legacy entry point.**

```bash
JOBS=1 SCAN_OUT=logs/example-run \
  python scripts/scan_c1c5.py ExampleProtocol
```

Multiple project directory names can be supplied in the same command. Use a
separate output directory for every model/configuration. The copied scanner uses
a fixed output limit of 900 tokens per candidate; it is not configured through
an environment variable.

For compiler setup, checkpoint behavior, and troubleshooting, see the
[first-run guide](docs/QUICKSTART.md).

## Outputs

The scanner writes one JSON file per project under `SCAN_OUT`.

| Field | Meaning |
| --- | --- |
| `status` | Project-level execution status, not proof of full coverage |
| `n_candidates` | Number of candidates returned by static discovery |
| `all_verdicts` | Candidate outcomes, including recorded errors or uncertainty |
| `findings` | Candidates receiving a positive historical mechanism judgment |
| `usage` | Recorded LLM token usage and call elapsed time |

An existing project JSON causes that project to be skipped. Checkpointing is
project-level, not request-level. A project can finish with candidate errors,
and recorded API time is not the complete tool's end-to-end runtime. See
[output interpretation](docs/OUTPUT_FORMAT.md).

## Benchmark evaluation

The explicit Reachable-65 selection is stored in
`benchmarks/reachable65/evaluation_only.json`:

| Category | Positive labels |
| --- | ---: |
| C1 | 15 |
| C2 | 14 |
| C3 | 10 |
| C4 | 14 |
| C5 | 12 |
| **Total** | **65** |

These are historical evaluation labels, not a new source-validation result.
They are not loaded by the scanner or sent to the model. The larger historical
CSV pool and the later 62-root benchmark are separate artifacts.

After collecting per-project outputs, run the offline evaluator:

```bash
python scripts/evaluate_reachable65.py \
  --scan-dir logs/example-run \
  --output logs/reachable65-recognition.json
```

This command does not call an API. It uses the original project/subtype/file-alias
matcher and reports **legacy recognition recall**, class-wise counts, missing
projects, recorded errors, and unmatched alerts. A one-project example run is
not a complete benchmark evaluation. The output path must not already exist.

The wrapper does not compute strict precision or F1 without source review and
aligned evaluation units. An unmatched alert is not automatically false, and a
label match is not independent proof of a current vulnerability. See
[evaluation semantics](docs/EVALUATION.md).

## Additional utilities

| Script | Purpose | Inference API |
| --- | --- | --- |
| `scan_c1c5.py` | Candidate discovery and LLM judgment | Yes |
| `evaluate_reachable65.py` | Offline statistics on the frozen 65-label selection | No |
| `eval_stablecoin_specific.py` | Original evaluator using the historical CSV pool | No |
| `rerun_candidates_from_log.py` | Same-candidate source-excerpt reruns and legacy ablations | Yes |
| `adjudicate_same_candidate_source.py` | Historical mechanism-level review | Yes |
| `build_realworld_validation_packet.py` | Prepare review packets from local findings | No |
| `cross_defect_c1c5.py` | Optional cross-defect composition analysis | Yes |

Optional review retains historical mechanism semantics; it is not an automatic
current-defect confirmation stage. Source-excerpt reruns and project scans do not
necessarily give the model the same context. Composition is disabled by default.

## Repository structure

```text
StableGuard-legacy/
  stableguard/                 Project loader, detectors, prompts, LLM client
  static_screening/lib/        C1-C5 / S01-S19 taxonomy
  config/knowledge_base/       Original rule knowledge base
  scripts/                    Scan, rerun, review, and evaluation entry points
  benchmarks/reachable65/      Evaluation-only metadata
  examples/                   Project-list and experiment-record templates
  dataset/                    Local project inputs; ignored by Git
  logs/                       Local run outputs; ignored by Git
  provenance/                 Source identities and historical pins
  docs/                       Detailed usage and evaluation documentation
  .github/                    Issue and pull-request templates
  .env.example                Placeholder environment configuration
  pyproject.toml              Editable-install metadata
  requirements.txt            Dependency requirements
  stablecoin_specific_full.csv Historical finding pool
```

## Reproducibility and limitations

The five core files match their recorded historical method hashes. Copied support
utilities are separately inventoried; not every utility or dependency is pinned
by those historical records. The generic scanner is not the locked experiment
executor used for every historical run.

Context recovery is heuristic: it uses first-by-name callee lookup, a depth limit,
and character limits. Compilation fallback can provide partial coverage. The
matcher does not establish exact function, source-version, or defect-root identity.
These behaviors are preserved and described in the [architecture notes](docs/ARCHITECTURE.md).

Reproducing historical numbers also requires the exact project revisions,
dependencies, model configuration, inputs, and review records. This code export
does not include the complete environment or guarantee historical performance.
Use the [reproducibility guide](docs/REPRODUCIBILITY.md) to record a new run.

## Documentation

| Document | Purpose |
| --- | --- |
| [Quick start](docs/QUICKSTART.md) | First execution and troubleshooting |
| [Configuration](docs/CONFIGURATION.md) | Provider settings, limits, retries, optional utilities |
| [Architecture](docs/ARCHITECTURE.md) | Actual legacy execution path |
| [Outputs](docs/OUTPUT_FORMAT.md) | Status, alert, error, and cost interpretation |
| [Evaluation](docs/EVALUATION.md) | Benchmark scope and metric boundaries |
| [Reproducibility](docs/REPRODUCIBILITY.md) | Source, model, and environment records |
| [Provenance](docs/PROVENANCE.md) | Export origins and checksum scope |
| [Release checklist](docs/RELEASE_CHECKLIST.md) | Remaining publication decisions |

## Contributing, security, and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for change boundaries and
[SECURITY.md](SECURITY.md) for handling credentials and sensitive findings.
Repository changes are recorded in [CHANGELOG.md](CHANGELOG.md).

**License pending:** no software license has been selected on behalf of the
authors. The owner must add a license and review audit-metadata redistribution
rights before public release. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Author information, the final repository URL, and publication citation will be
added after confirmation; this export does not invent them.
