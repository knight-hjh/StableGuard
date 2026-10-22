"""
static_screening -- Stage-2 pure-static pre-screening of stablecoin defects.

Goal: high-recall, LLM-free static detection across the full dataset to measure
the real-world *distribution / prevalence* of the 12 deterministic defects.
This is separate from the LLM+static hybrid method (which answers "how good is
our detection?"); this package answers "do these defects exist and how common
are they?".
"""
