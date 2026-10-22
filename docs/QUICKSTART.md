# First-run guide

This guide describes commands for the user to execute. Packaging this repository
did not execute these commands or establish a passing installation test.

## Prepare the environment

Use Python 3.10 or newer and a POSIX environment. Create a separate environment
and install `requirements.txt` as shown in the main README. Work from this
repository root so `dataset/`, `config/`, and `logs/` resolve consistently.

The Solidity compiler and project toolchain are separate dependencies. For a
Foundry or Hardhat project, preserve its own dependency locks, remappings, compiler
settings, and build configuration. Do not change a pragma or replace dependencies
with their latest versions merely to obtain a successful parse.

Before invoking an untrusted project's build configuration, inspect it and use
an appropriately isolated environment. Build tools can execute project scripts.

## Configure credentials explicitly

Create `.env` from `.env.example` and populate the provider URL, key, and model
locally. Ensure exported environment variables do not unintentionally override
your chosen `.env` values. The scripts use python-dotenv without forcing an
override of existing environment variables.

If running this release inside another workspace, do not rely on dotenv's parent
directory search: it may find that workspace's credentials. Use a dedicated
checkout/environment and an explicitly prepared local `.env`.

Do not enable both providers' thinking options without confirming that the
selected endpoint supports those fields. A model name alone does not configure
thinking or guarantee a particular provider-side model version.

## Prepare inputs

An example layout is:

```text
dataset/
  ExampleProtocol/
    contracts/
    foundry.toml or hardhat.config.* or the original plain-source layout
    original dependency locks and dependencies
```

The project argument is the directory name under `dataset/`, not a finding ID.
For historical evaluation, the exact source revision matters. Full project inputs
are not part of this code export.

## Start one explicitly authorized scan

The command below calls the configured inference API:

```bash
JOBS=1 SCAN_OUT=logs/example-full python scripts/scan_c1c5.py ExampleProtocol
```

Do not use a prior model's output directory for a new configuration. The historical
worker skips an existing per-project JSON, including files containing failures.
An interrupted project with no completed output may be recomputed and charged
again. There is no per-request continuation ledger in this generic entry point.

## Multiple projects or a restricted subtype set

These commands also call the inference API:

```bash
JOBS=1 SCAN_OUT=logs/two-projects \
  python scripts/scan_c1c5.py ExampleProtocol AnotherProtocol

JOBS=1 SUBS=S09,S10 SCAN_OUT=logs/subtype-subset \
  python scripts/scan_c1c5.py ExampleProtocol
```

With no positional project names, the scanner reads a project-list file. Replace
the placeholder names in `examples/project-list.example.txt` with the intended
local directory names before using it:

```bash
PROJECT_LIST=examples/project-list.example.txt JOBS=1 SCAN_OUT=logs/project-list \
  python scripts/scan_c1c5.py
```

The original scanner filters out directory names that do not exist. A completed
command does not prove that every requested project was actually analyzed.

## Inspect outputs before interpreting results

Use the saved project status, candidate count, `all_verdicts`, and errors to
separate compilation, transport, response-format, and semantic outcomes.
`status=ok` does not guarantee that every candidate has a usable judgment.
See [OUTPUT_FORMAT.md](OUTPUT_FORMAT.md).

The offline evaluator can run without model credentials:

```bash
python scripts/evaluate_reachable65.py \
  --scan-dir logs/example-full \
  --output logs/example-recognition.json
```

It retains the full 65-label denominator and lists missing projects. It does not
turn a partial run into a completed benchmark experiment.

## Troubleshooting

| Symptom | First distinction to make |
| --- | --- |
| No projects analyzed | Confirm directory names and run from the repository root |
| Compiler/import failure | Check the exact revision's compiler, dependencies, and remappings |
| Fallback parsing succeeds | Determine which files were actually covered; success is not full coverage |
| Missing credentials or unsupported parameter | Check selected environment values and endpoint capabilities |
| Empty or truncated model output | Record the technical failure; the scan output limit is fixed at 900 tokens |
| Project is skipped | An output JSON already exists; preserve it and select a separate run directory |
| Unexpectedly high alert count | Positive values use historical mechanism recognition, not confirmed exploitability |

Do not silently delete failed outputs, switch models within a run, or reinterpret
technical failures as negative judgments. Changing the output limit or prompt
defines a changed configuration and must be documented separately.
