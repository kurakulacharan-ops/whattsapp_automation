"""
Extracts structured data (place, lat/long, date, time) from the burned-in
GPS Map Camera overlay on employee selfies.

TESTED against a real sample image (Individual_pic.jpeg, 28/08/2026 submission)
— raw Tesseract OCR on the full image reliably captured all fields with no
preprocessing needed:

    ie GPS Map Camera
    Ashti, Maharashtra, India
    R53f+rwr, Maliwada, Ashti, Maharashtra 414203, India
    Lat 18.804903° Long 75.174764°
    Friday, 28/08/2026 09:27 AM GMT +05:30

All three regex extractions (lat/long, date/time, place) matched correctly
against this real output. Worth re-testing against a handful more real
employee submissions once live traffic starts — overlay position/wording
can vary slightly by phone/app version, and this was validated against
one sample only.
"""
import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Optional
import os
from zoneinfo import ZoneInfo

import pytesseract


if os.name == "nt" and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from PIL import Image, ImageOps
from pydantic import BaseModel

logger = logging.getLogger("ocr")

LAT_LONG_PATTERN = re.compile(
    r"(?:Lat(?:itude)?|अक्षांश)\s*[:：]?\s*([+\-]?[0-9][0-9.,: \t]*[0-9])"
    r"[.,:+\-]*\s*(?:°|Â°|[\"'])?\s+"
    r"(?:Long(?:itude)?|रेखांश)\s*[:：]?\s*([+\-]?[0-9][0-9.,: \t]*[0-9])"
    r"[.,:]*(?:°|Â°|[\"'])?",
    re.IGNORECASE,
)
DATETIME_PATTERN = re.compile(
    r"(?im)(?:[\w\u0900-\u097f]+,?\s+)?"
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(AM|PM|पूर्वाह्न|अपराह्न|सकाळी|दुपारी|सुबह|दोपहर|शाम|रात)?\s*"
    r"(?:GMT|UTC|IST|जीएमटी)?\s*([+\-]\d{2}:\d{2})?"
)
PLACE_PATTERN = re.compile(
    r"(?im)^\s*([^\r\n,]+,\s*[^\r\n,]+,\s*(?:India|भारत))\s*$"
)
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _parse_overlay_timestamp(text: str) -> datetime | None:
    match = DATETIME_PATTERN.search(text)
    if match is None:
        return None

    date_str, time_str, meridiem, tz_offset = match.groups()
    normalized_meridiem = {
        "पूर्वाह्न": "AM",
        "सकाळी": "AM",
        "सुबह": "AM",
        "अपराह्न": "PM",
        "दुपारी": "PM",
        "दोपहर": "PM",
        "शाम": "PM",
        "रात": "PM",
    }.get(meridiem, meridiem)
    if normalized_meridiem and int(time_str[:2]) <= 12:
        normalized_time = f"{time_str} {normalized_meridiem}"
    else:
        normalized_time = time_str
    timezone = datetime.strptime(tz_offset, "%z").tzinfo if tz_offset else INDIA_TIMEZONE

    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        for time_format in (
            "%I:%M:%S %p",
            "%H:%M:%S",
            "%I:%M %p",
            "%H:%M",
        ):
            try:
                parsed = datetime.strptime(
                    f"{date_str} {normalized_time}",
                    f"{date_format} {time_format}",
                )
                return parsed.replace(tzinfo=timezone)
            except ValueError:
                continue
    return None


def _normalize_coordinate(value: str, maximum_degrees: float) -> float:
    normalized = re.sub(r"\s+", "", value).rstrip(".,:+-")
    normalized = normalized.replace(",", ".").replace(":", ".")
    coordinate = float(normalized)
    if abs(coordinate) > maximum_degrees:
        sign = "-" if normalized.startswith("-") else ""
        digits = normalized.lstrip("+-").replace(".", "")
        if len(digits) < 3:
            raise ValueError(f"Invalid coordinate: {value}")
        coordinate = float(f"{sign}{digits[:2]}.{digits[2:]}")
    if abs(coordinate) > maximum_degrees:
        raise ValueError(f"Invalid coordinate: {value}")
    return coordinate


class OverlayData(BaseModel):
    raw_text: str
    place: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[datetime] = None
    extraction_complete: bool = False
    exif_timestamp: Optional[datetime] = None


def extract_overlay_data(image_bytes: bytes) -> OverlayData:
    """
    Run OCR on an employee's selfie and extract the GPS Map Camera overlay
    fields needed for geofence + shift-window checks.
    """
    img = Image.open(BytesIO(image_bytes))
    full_text = pytesseract.image_to_string(img, lang="eng+hin+mar")

    width, height = img.size
    overlay_crop = img.crop((0, int(height * 0.48), width, height)).convert("L")
    overlay_crop = ImageOps.autocontrast(overlay_crop)
    overlay_crop = overlay_crop.resize(
        (overlay_crop.width * 3, overlay_crop.height * 3),
        Image.Resampling.LANCZOS,
    )
    overlay_text = pytesseract.image_to_string(
        overlay_crop,
        lang="eng+hin+mar",
        config="--psm 6",
    )
    raw_text = "\n".join(part for part in (full_text, overlay_text) if part.strip())
    normalized_text = raw_text.translate(DEVANAGARI_DIGITS)

    result = OverlayData(raw_text=raw_text)
    try:
        exif = img.getexif()
        # DateTimeOriginal=36867, DateTimeDigitized=36868, DateTime=306
        for tag in (36867, 36868, 306):
            value = exif.get(tag)
            if value:
                try:
                    result.exif_timestamp = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                    break
                except ValueError:
                    pass
    except Exception:
        logger.debug("EXIF metadata unavailable", exc_info=True)

    if match := LAT_LONG_PATTERN.search(normalized_text):
        try:
            result.latitude = _normalize_coordinate(match.group(1), 90)
            result.longitude = _normalize_coordinate(match.group(2), 180)
        except ValueError:
            logger.warning(
                "Could not convert lat/long: %s, %s",
                match.group(1),
                match.group(2),
            )
    else:
        logger.warning("Could not extract lat/long from overlay")

    result.timestamp = _parse_overlay_timestamp(normalized_text)
    if result.timestamp is None:
        logger.warning("Could not extract date/time from overlay")

    if match := PLACE_PATTERN.search(raw_text):
        result.place = match.group(1).strip()

    result.extraction_complete = (
        result.latitude is not None
        and result.longitude is not None
        and result.timestamp is not None
    )

    return result
