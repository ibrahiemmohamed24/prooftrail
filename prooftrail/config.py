"""Single source of truth for models, budgets, paths and fairness constants.

Everything that must be *identical* between the baselines and ProofTrail lives
here so that the fairness of the comparison is enforced by code, not by
discipline. Do not add per-auditor model or token overrides.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data"
FROZEN_DIR = DATA_DIR / "frozen"          # committed: one folder per case
REPLAY_DIR = DATA_DIR / "replay"          # committed: cached LLM responses
REVIEW_DIR = DATA_DIR / "reviews" / "v1"  # committed: explicit human decisions
B1_REPLAY_DIR = REPLAY_DIR / "auditors" / "b1"
STATE_DIR = DATA_DIR / "state"            # ignored: live SQLite files
EVIDENCE_DIR = PROJECT_ROOT / "evidence" / "runs"
REVIEW_PACK_DIR = PROJECT_ROOT / "evidence" / "review-pack-v1"
BENCHMARK_DIR = EVIDENCE_DIR / "benchmark"

# --------------------------------------------------------------------------- #
# Legacy global model default used by the paid agent and the B1 contract.
# The executable benchmark must replace implicit inheritance with an explicit
# evaluation spec (provider, model and limits) before publishing any result.
# The frozen v1 agent dataset itself records its real Gemini model per turn.
# --------------------------------------------------------------------------- #
DEFAULT_MODEL = "claude-opus-5"
MODEL = os.environ.get("PROOFTRAIL_MODEL", DEFAULT_MODEL)

# USD per 1M tokens (Anthropic first-party API, checked 2026-08-28).
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class UnknownModelPricingError(KeyError):
    """A model without an entry in ``PRICING_PER_MTOK`` must never be billed blindly."""


def pricing_for(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens. Unknown models are refused, not guessed:
    a fallback price could be lower than the real one and silently defeat the
    budget guard."""
    try:
        return PRICING_PER_MTOK[model]
    except KeyError:
        raise UnknownModelPricingError(
            f"no price is configured for model {model!r}; add it to PRICING_PER_MTOK "
            f"(known: {', '.join(sorted(PRICING_PER_MTOK))}) before running live"
        ) from None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost of one call at the configured first-party price."""
    inp, out = pricing_for(model)
    return (input_tokens * inp + output_tokens * out) / 1_000_000


# --------------------------------------------------------------------------- #
# Budget guard (live mode only)
# --------------------------------------------------------------------------- #
BUDGET_USD = float(os.environ.get("PROOFTRAIL_BUDGET_USD", "30"))
COST_LEDGER_PATH = REPLAY_DIR / "cost_ledger.jsonl"


# --------------------------------------------------------------------------- #
# Auditor limits. B1 uses one model call. The current ProofTrail implementation
# is fully deterministic and uses zero calls; a future LLM extractor must use
# these same caps and be evaluated as a separately named ablation.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditorLimits:
    """Identical caps for every auditor. Changing one changes all."""

    max_output_tokens: int = 4096
    effort: str = "high"
    # Maximum for any auditor configuration that uses an LLM. B1 is one-shot.
    max_llm_calls_per_case: int = 1


AUDITOR_LIMITS = AuditorLimits()


@dataclass(frozen=True)
class AgentLimits:
    """Caps for the *refund agent* whose behaviour we audit (data creation)."""

    max_output_tokens: int = 4096
    max_turns: int = 12
    effort: str = "medium"


AGENT_LIMITS = AgentLimits()


# --------------------------------------------------------------------------- #
# Scenario generation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScenarioConfig:
    instances_per_family: int = 4
    # Seeds are fixed so `prooftrail cases generate` is byte-reproducible.
    seeds: tuple[int, ...] = field(default_factory=lambda: (0, 1, 2, 3))


SCENARIO_CONFIG = ScenarioConfig()

# Simulated clock start for every case (ISO 8601, UTC). Deterministic timestamps
# make ledger hashes reproducible across machines.
SIM_CLOCK_START = "2026-08-28T09:00:00+00:00"
SIM_CLOCK_STEP_SECONDS = 7
