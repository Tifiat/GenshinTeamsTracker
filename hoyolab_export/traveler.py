"""Account-only Traveler identity; negative IDs are local, never game IDs.

The first observed element retains the source ID to preserve saved references.
Other elements use the finite local namespace below. Source identity (including
gender) and explicit element, not that account-local anchor, identify PvP rules.
"""
from __future__ import annotations

TRAVELER_SOURCE_IDS = frozenset({10000005, 10000007})
TRAVELER_ELEMENTS = ("Anemo", "Geo", "Electro", "Dendro", "Hydro", "Pyro", "Cryo")
_VARIANTS = {
    -(source_id * 10 + index): (source_id, element)
    for source_id in TRAVELER_SOURCE_IDS
    for index, element in enumerate(TRAVELER_ELEMENTS, 1)
}


def traveler_source_id(character_id: object) -> int | None:
    try:
        value = int(str(character_id))
    except (TypeError, ValueError):
        return None
    if value in TRAVELER_SOURCE_IDS:
        return value
    variant = _VARIANTS.get(value)
    return variant[0] if variant else None


def is_traveler_id(character_id: object) -> bool:
    return traveler_source_id(character_id) is not None


def traveler_element(character_id: object, element: object = "") -> str:
    if not is_traveler_id(character_id):
        return ""
    explicit = str(element or "").strip().casefold()
    variant = _VARIANTS.get(int(str(character_id)))
    normalized = next((item for item in TRAVELER_ELEMENTS if item.casefold() == explicit), "")
    # A supplied contradictory/unknown element must never silently pick another.
    if explicit:
        return normalized if variant is None or variant[1] == normalized else ""
    return variant[1] if variant else ""


def traveler_variant_id(source_id: int, element: str) -> int:
    if source_id not in TRAVELER_SOURCE_IDS or element not in TRAVELER_ELEMENTS:
        raise ValueError("Traveler requires its source game ID and a known element")
    return -(source_id * 10 + TRAVELER_ELEMENTS.index(element) + 1)


def traveler_catalog_name(character_id: object, element: object) -> str:
    selected = traveler_element(character_id, element)
    return f"Traveler ({selected})" if selected else "Traveler"
