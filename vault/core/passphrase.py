"""Conservative guidance, not an estimate of password entropy."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Strength:
    label: str
    score: int
    tip: str


def strength(value: str) -> Strength:
    if len(value) < 12 or len(set(value.casefold())) < 5:
        return Strength("Weak", 1, "Use at least 12 characters; try 4+ random words.")
    if len(value) >= 20 and len(set(value.casefold())) >= 10:
        return Strength("Strong", 3, "Good length. Choose random words, not a quote or personal details.")
    return Strength("Okay", 2, "Make it longer: use 4+ random, unrelated words.")
