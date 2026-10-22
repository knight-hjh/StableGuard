# Local outputs

The scanner writes per-project JSON files to `SCAN_OUT`, normally below this
directory. They contain model judgments, source locations, errors, and usage.
Do not treat `findings` as independently confirmed vulnerabilities.

No historical model response or credential is bundled. This directory is ignored
by Git except for this README. Keep configurations and runs separate; existing
per-project outputs cause the historical scanner to skip that project.

Optional local inputs include `build_probe.json`, `inherit_resolver.json`, and
project-list files. They are not bundled and should not be silently assumed when
claiming reproduction of a past experiment.
