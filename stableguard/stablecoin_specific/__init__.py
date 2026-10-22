"""Parallel detection module for the C1-C5 / S01-S19 stablecoin-specific taxonomy.

Independent of the 40-type FactType/router/agent machinery (which stays untouched).
Each detector is a slither-based function that yields candidate locations tagged with a
sub-type (S01..S19). The driver `run_detectors` aggregates them; the hybrid stage (N4)
then sends each candidate to an LLM with the matching C1-C5 KB for the precision verdict.
"""
from .detectors import Candidate, run_detectors, DETECTORS  # noqa: F401
