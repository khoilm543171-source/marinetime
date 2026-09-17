from __future__ import annotations

from typing import Any


def use_permissions(alu: dict[str, Any]) -> set[str]:
    """Return allowed retrieval/use modes after deterministic gating."""
    from marinetime.validation.safety import validate_alu

    decision = validate_alu(alu)
    modes = set()
    if decision.accepted_for_reference:
        modes.add("reference_mode")
    if decision.accepted_for_education:
        modes.add("educational_mode")
    if decision.accepted_for_operational_use:
        modes.add("operational_safety_mode")
    return modes
