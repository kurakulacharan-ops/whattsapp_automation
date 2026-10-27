"""Match OCR-extracted location labels to an assigned city or district locally."""

import unicodedata


def normalize_location_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(
        char if char.isalnum() else " " for char in without_marks
    ).split())


def place_contains_area(
    place: str | None,
    expected_area: str | None,
    match_level: str,
) -> bool | None:
    """Match a place name against an area without sending GPS to a third party.

    District matches return None when the photo label does not name the district;
    a locality/city label alone cannot establish district membership.
    """
    if not place or not place.strip() or not expected_area or not expected_area.strip():
        return None

    expected = normalize_location_name(expected_area)
    place_parts = [
        normalize_location_name(part)
        for part in place.split(",")
        if part.strip()
    ]
    if expected in place_parts:
        return True
    if match_level == "district":
        return None
    return False
