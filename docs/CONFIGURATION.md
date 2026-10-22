# Configuration and execution boundaries

## Provider configuration

The copied client reads `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`, and
`SILICONFLOW_MODEL`, even when an alternative OpenAI-compatible provider is used.
Use a local `.env` file or exported environment variables. No credential is bundled.

`SILICONFLOW_ENABLE_THINKING` adds the provider-specific `enable_thinking` field.
`DEEPSEEK_THINKING_TYPE` adds the `thinking.type` field. These are different wire
formats; configure only fields supported by the selected endpoint.

Leaving a thinking field unset does not prove that thinking is disabled at the
provider. This client does not automatically verify model aliases or normalize
provider-specific model identities.

## Scanner settings

| Setting | Historical behavior |
| --- | --- |
| Input root | `dataset/projects/`, relative to the working directory |
| `SCAN_OUT` | Defaults to `logs/c1c5_scan` |
| `JOBS` | Defaults to 4; the example configuration selects 1 |
| `SUBS` | Optional comma-separated subtype IDs |
| `SCAN_PARSE_TIMEOUT` | Defaults to 420 seconds |
| `NO_INLINE=1` | Disables heuristic callee augmentation |
| `ABLATION_MODE` | `full`, `no_facts`, `no_routing`, or `no_grouped_agent` |
| `RUN_CROSS=1` | Adds an optional, separately charged composition stage |
| `SOLC_VERSION` | Local compiler selection; install the exact compiler separately |
| `SG_IGNORE_COMPILE` | Reuse pre-existing build artifacts for selected projects |

The scan and candidate-rerun scripts hard-code `max_tokens=900`. This is not
changed by an environment variable in the copied implementation. Other historical
experiment drivers used different transports or limits; this export does not
claim that the generic scan command reproduces every experiment configuration.

## Retries, errors, and checkpoints

The SDK's hidden retries are disabled. The copied client itself defaults to at
most three attempts for handled API errors, with exponential waiting. There is
no aggregate spending limit and no general first-error batch stop. Usage totals
primarily account for successfully returned calls, not necessarily all provider
charges associated with failed attempts.

The scanner records candidate exceptions and continues. A project-level `ok`
status is not proof that every candidate received a valid response. The generic
parser is also less strict than the locked experiment executors.

Output is checkpointed per project, not per request. An existing project JSON
is skipped even when it contains errors; an interrupted project without a saved
JSON may be recomputed. Preserve original outputs and choose a new output
directory when changing model or settings. Do not mix configurations silently.

## Optional utilities

`rerun_candidates_from_log.py` uses source excerpts around recorded locations;
it is not identical to the scanner's augmented function context. It expects the
input logs to be within the repository checkout.

`adjudicate_same_candidate_source.py` also uses historical type/mechanism
semantics and directly credits dataset matches. Do not present its acceptance
fraction as independently source-confirmed exploitability precision.

Composition can use `SOURCE_LOADER=filesystem` for source excerpts or its generic
compiler loader. Workspace-specific direct-load recipes are not bundled.
