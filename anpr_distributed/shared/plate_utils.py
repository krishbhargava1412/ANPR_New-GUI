"""
Plate text normalization and validation utilities.

Ported directly from legacy_backend.py — all core logic preserved verbatim.
Shared between edge (Jetson) and server (DRDO) components.
"""
from __future__ import annotations

import re
import string


# ── Constants ──────────────────────────────────────────────────────────────────
PLATE_REGEX = r"^(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{6,10}$"
STRICT_PLATE_REGEX = r"^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{4}$"
OCR_MIN_SCORE = 0.45  # Raised from 0.35 for production (fewer false positives)

# OCR correction mappings for positional format (AA##AA####)
dict_char_to_int = {
    "O": "0",
    "I": "1",
    "J": "3",
    "A": "4",
    "G": "6",
    "S": "5",
}

dict_int_to_char = {
    "0": "O",
    "1": "I",
    "3": "J",
    "4": "A",
    "6": "G",
    "5": "S",
}

VALID_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BH", "BR", "CG", "CH", "DD", "DL", "DN", "GA",
    "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN",
    "MP", "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}


# ── Validation Functions ──────────────────────────────────────────────────────
def license_complies_format(text: str) -> bool:
    """Return True if *text* matches a valid plate format.

    Ten-character plates are validated against the Indian positional format
    (AA##AA####). Plates of 6–9 characters are accepted if they match the
    configurable PLATE_REGEX from settings.
    """
    if len(text) == 10:
        return (
            (text[0] in string.ascii_uppercase or text[0] in dict_int_to_char)
            and (text[1] in string.ascii_uppercase or text[1] in dict_int_to_char)
            and (text[2].isdigit() or text[2] in dict_char_to_int)
            and (text[3].isdigit() or text[3] in dict_char_to_int)
            and (text[4] in string.ascii_uppercase or text[4] in dict_int_to_char)
            and (text[5] in string.ascii_uppercase or text[5] in dict_int_to_char)
            and (text[6].isdigit() or text[6] in dict_char_to_int)
            and (text[7].isdigit() or text[7] in dict_char_to_int)
            and (text[8].isdigit() or text[8] in dict_char_to_int)
            and (text[9].isdigit() or text[9] in dict_char_to_int)
        )
    return bool(re.match(PLATE_REGEX, text))


def format_license(text: str) -> str:
    """Apply position-based OCR-correction for 10-char Indian plates.

    For plates shorter than 10 characters (allowed by PLATE_REGEX) the text is
    returned as-is because the positional correction map only applies to the
    Indian AA##AA#### format.
    """
    if len(text) != 10:
        return text
    license_plate_ = ""
    mapping = {
        0: dict_int_to_char,
        1: dict_int_to_char,
        4: dict_int_to_char,
        5: dict_int_to_char,
        2: dict_char_to_int,
        3: dict_char_to_int,
        6: dict_char_to_int,
        7: dict_char_to_int,
        8: dict_char_to_int,
        9: dict_char_to_int,
    }
    for index in range(10):
        license_plate_ += mapping[index].get(text[index], text[index])
    return license_plate_


def validate_state_code(text: str) -> bool:
    """Check if the first two characters are a valid Indian state code."""
    if len(text) < 2:
        return False
    # Apply OCR correction to first 2 chars before checking
    corrected = ""
    for i in range(2):
        corrected += dict_int_to_char.get(text[i], text[i])
    return corrected in VALID_STATE_CODES


def normalize_plate_text(text: str) -> str | None:
    """Normalize raw OCR text into a clean plate number, or None if invalid."""
    text = text.upper().replace(" ", "")
    if not text:
        return None

    # Enforce state code validation for Indian plates
    if len(text) >= 6 and not validate_state_code(text):
        return None

    if len(text) == 10:
        if not license_complies_format(text):
            return None
        return format_license(text)
    if license_complies_format(text):
        return text
    return None
