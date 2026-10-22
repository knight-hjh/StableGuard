# StableGuard (Legacy)

Static analysis and LLM-assisted recognition of backing-related defect mechanisms
in stablecoin smart contracts. This repository packages the legacy C1-C5 scanner,
its rule knowledge base, the 65-instance Dataset, and inspectable project sources.
It is not the newer M0-M3 implementation.

## Repository structure

```text
StableGuard-legacy/
  stableguard/                    Legacy detector, loader and LLM client
  static_screening/               Subtype definitions and static support
  config/knowledge_base/          C1-C5 / S01-S19 rule entries
  scripts/                       Scanning and offline evaluation commands
  dataset/
    README.md                    Dataset scope and source-version limitations
    instances.json               65 records, labels and source bindings
    projects.json                Repository/version inventory and file counts
    source-files.json            Per-file paths, sizes and SHA-256 values
    project-list.txt             The 10 analysis project names
    projects/
      BAI/ BOB/ DAI+/ DEURO/ EURA/ EURE/ EUSD/ GYEN/ LVLUSD/ MIM/
      snapshots/                 Available historical reference source trees
    version-alignment.json       Existing version-alignment evidence
    excluded-files.json          Files/directories not included in this export
  docs/                          Configuration, outputs and reproducibility
  provenance/                    Original identities and packaging changes
  examples/                      Configuration and experiment-record examples
  logs/                          Generated outputs (ignored by Git)
```

There is one `dataset/` directory, not a separate benchmark directory. The source
trees are physically included under `dataset/projects/`; JSON files describe and
link those trees rather than substituting for them.

## Dataset

| Category | Historical records |
| --- | ---: |
| C1: Backing Mis-Valuation | 15 |
| C2: Unbacked Issuance | 14 |
| C3: Supply-Backing Ledger Desynchronization | 10 |
| C4: Liquidation and Solvency Failure | 14 |
| C5: Par-Redemption Violation | 12 |
| Total | 65 |

The 65 records cover 10 projects. This export contains 32 source
trees: 10 analysis working-tree copies and 22 historical
reference snapshots. Together they contain 21,337
packaged files, including 10,090 Solidity
files. Counts include copies shared across different versions, not unique content.

The original IDs, categories and historical matching fields are retained.
**A packaged source tree is not automatically the vulnerable audit version.**
Existing source-alignment records contain differing versions, missing pins and
duplicate annotations. Each instance records the available source candidates and
the remaining version gaps; no label was silently changed during packaging.
See [Dataset documentation](dataset/README.md).

## Requirements

- Python 3.10 or newer and a Linux/POSIX environment.
- The Python packages in `requirements.txt`.
- A project-compatible Solidity compiler and the project's pinned dependencies.
- An authorized OpenAI-compatible API endpoint and an exact model identifier.

Project source and available vendored libraries are included. Installed
`node_modules`, compiler binaries and build caches are not included. Dependency
lockfiles and build configuration are preserved where available; restore the
versions they specify rather than installing arbitrary latest dependencies.

## Installation and configuration

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure the legacy environment-variable names in your local `.env`:

```dotenv
SILICONFLOW_API_KEY=YOUR_API_KEY
SILICONFLOW_BASE_URL=https://YOUR_PROVIDER/v1
SILICONFLOW_MODEL=EXACT_PROVIDER_MODEL_ID
JOBS=1
RUN_CROSS=0
PROJECT_LIST=dataset/project-list.txt
```

The variable prefix is historical; the configured URL determines the provider.
Do not commit real credentials. Keep the repository checkout: the knowledge base
is loaded from a checkout-relative path. Standalone-wheel operation is not claimed.

## Run the scanner

Run commands from this repository root. **Scanning sends source and subtype rules
to the configured API and may incur charges.** The legacy scanner has no global
token-budget enforcement. Its default per-request output limit remains 900 tokens.

Scan one packaged analysis project:

```bash
JOBS=1 SCAN_OUT=logs/deuro-run python scripts/scan_c1c5.py DEURO
```

Scan the ten projects listed in the Dataset:

```bash
JOBS=1 PROJECT_LIST=dataset/project-list.txt SCAN_OUT=logs/dataset-run \
  python scripts/scan_c1c5.py
```

These commands are usage instructions, not commands executed while packaging.
The snapshot directory is reference material and is not silently scanned or
merged with the analysis trees. Compilation may require project-specific setup.
Use a separate output directory for each run: the legacy scanner skips an existing
per-project result file, including one that records a failure.

## How rules reach the LLM

The static detector assigns a candidate subtype. The prompt builder selects that
subtype's definition, positive signals, exclusions and financial impact from
`config/knowledge_base/c1c5_kb.yaml`. It combines them with the candidate function
and heuristically selected callee bodies. Default requests do not contain all
subtype rules, Dataset labels or previous evaluation answers.

The historical system prompt is **FIX-AGNOSTIC**: a positive mechanism/type match
can be returned even for guarded or patched code. Such an alert is not by itself
a confirmed exploitable defect. The default scan does not implement an independent
adversarial-review and context-feedback loop. These semantics have not been changed.

## Outputs and offline evaluation

Each project result includes `status`, `n_candidates`, `all_verdicts`,
`findings` and recorded API `usage`. A project status of `ok` does not establish
that every candidate produced a valid response. API elapsed time is not total
tool end-to-end time.

After freezing scan outputs, use the Dataset labels locally:

```bash
python scripts/evaluate_reachable65.py \
  --scan-dir logs/dataset-run \
  --labels dataset/instances.json \
  --output logs/dataset-recognition.json
```

The wrapper makes no API calls. It preserves the historical project/subtype/file-
alias matcher and reports recognition recall over all 65 records, including missing
projects in the denominator. It does not certify exact vulnerable roots or compute
strict Precision/F1 without source review. An unmatched alert is not automatically
a false positive. The output file must not already exist.

## Documentation

- [Dataset and source layout](dataset/README.md)
- [Quick start](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Output fields](docs/OUTPUT_FORMAT.md)
- [Evaluation semantics](docs/EVALUATION.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Export provenance](docs/PROVENANCE.md)
- [Publication checklist](docs/RELEASE_CHECKLIST.md)

## Publication status and licensing

Local source packaging and documentation are prepared. No compilation, tests,
installation checks, API experiments, Git initialization or GitHub upload were run
as part of this revision. Dataset-path defaults in the exported scripts were
adapted; detector logic, prompts, rules and matching criteria were not changed.

Upstream source notices are retained where present. The owner still needs to
choose StableGuard's license, review redistribution terms, supply author/citation
details and perform separately authorized runtime validation before calling this
a fully validated reproduction package. See [third-party notices](THIRD_PARTY_NOTICES.md),
[contribution guidance](CONTRIBUTING.md) and [security reporting](SECURITY.md).
