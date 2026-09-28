"""Entity profiles for the synthetic corpus.

Order matters: the first 10 profiles already cover every detector D01-D14 and
data-quality checks Q01-Q04, keep at least two entities per sector for peer
comparison, include three fully healthy entities and both innocent
look-alikes. `--entities N` simply takes the first N profiles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Fixed end of the reporting window so runs are reproducible across dates.
PERIOD_END = "2026-06-30"


@dataclass(frozen=True)
class EntityProfile:
    entity_id: str
    name: str
    sector: str
    size_tier: str
    #: planted fault codes handled by generator/faults.py
    faults: tuple[str, ...] = ()
    #: label used in the printed summary and in ground_truth.json
    role: str = "faulty"
    #: multiplies the baseline alert volume for this tier
    volume_factor: float = 1.0
    notes: str = ""
    #: extra flags consumed by faults.py / the base generator
    flags: dict = field(default_factory=dict)


TIER_SPECS: dict[str, dict] = {
    "small": {"assets": (50, 95), "analysts": (3, 6), "alerts_per_day": (24, 46)},
    "medium": {"assets": (150, 300), "analysts": (8, 18), "alerts_per_day": (85, 170)},
    "large": {"assets": (330, 600), "analysts": (22, 40), "alerts_per_day": (210, 420)},
}

PROFILES: list[EntityProfile] = [
    EntityProfile(
        "E001", "Northern Grid Transmission Co.", "power", "large",
        role="healthy", notes="Reference-quality SOC used as a peer baseline.",
    ),
    EntityProfile(
        "E002", "Deccan Power Distribution Ltd.", "power", "medium",
        faults=("D01", "D02", "D08", "Q01"),
        notes="Closes criticals in seconds, never escalates, games the 30-min SLA.",
    ),
    EntityProfile(
        "E003", "Meridian National Bank", "banking", "large",
        role="healthy", notes="Mature SOC, strong investigation notes.",
    ),
    EntityProfile(
        "E004", "Coastal Commercial Bank", "banking", "large",
        faults=("D03", "D04", "D05", "D13", "D14"),
        notes="Declared 15-min escalation but real median is hours; copy-paste notes.",
    ),
    EntityProfile(
        "E005", "Bharat Telecom Circle-West", "telecom", "large",
        role="healthy", notes="Healthy telecom SOC.",
    ),
    EntityProfile(
        "E006", "Skyline Telecom Services", "telecom", "medium",
        faults=("D06", "D07", "D09", "Q04"),
        notes="Same alert every day forever, flat effort, one super-human analyst.",
    ),
    EntityProfile(
        "E007", "Western Offshore Petro Ltd.", "oil_gas", "large",
        faults=("D10", "D11", "D12", "D14"),
        notes="Critical OT/DB assets silent, whole categories missing, volume collapse.",
    ),
    EntityProfile(
        "E008", "Refinery Operations East", "oil_gas", "medium",
        role="innocent_lookalike",
        flags={"automation_heavy": True},
        notes="INNOCENT: very fast closures, but all automated on info alerts.",
    ),
    EntityProfile(
        "E009", "Metro Rail Transit Authority", "transport", "medium",
        faults=("D02", "D06", "D13", "Q03"),
        notes="Criticals closed with no escalation record, recurring OT alerts ignored.",
    ),
    EntityProfile(
        "E010", "Coastal Freight Rail Corp.", "transport", "small",
        role="innocent_lookalike",
        volume_factor=0.28,
        flags={"tiny_volume": True},
        notes="INNOCENT: genuinely small estate, so every rate has a tiny sample.",
    ),
    EntityProfile(
        "E011", "Eastern Hydro Power Corp.", "power", "small",
        faults=("D01", "D04", "D08", "Q02"),
        notes="Small entity that still shows real execution gaps.",
    ),
    EntityProfile(
        "E012", "Unified Payments Bank", "banking", "medium",
        faults=("D05", "D07", "D12"),
        notes="Artefact-free notes and effort that does not track severity.",
    ),
]


def select_profiles(n: int) -> list[EntityProfile]:
    if n <= 0 or n > len(PROFILES):
        n = len(PROFILES)
    return PROFILES[:n]
