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
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(AM|PM|पूर्वाह्न|अपराह्न|सकाळी|दुपारी|सुबह|दोपहर|शाम|रात)?\s*"
    r"(?:GMT|UTC|IST|जीएमटी)?\s*([+\-]\d{2}:\d{2})?"
)
NAMED_DATE_PATTERNS = (
    (re.compile(r"(?i)(?<!\d)(\d{1,2})\s+([A-Za-z]{3,9})[,]?\s+(\d{4})(?!\d)"), "%d %B %Y"),
    (re.compile(r"(?i)(?<!\d)([A-Za-z]{3,9})[.,]?\s+(\d{1,2})[,]?\s+(\d{4})(?!\d)"), "%B %d %Y"),
)
TIME_PATTERN = re.compile(
    r"(?i)(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(AM|PM|पूर्वाह्न|अपराह्न|सकाळी|दुपारी|सुबह|दोपहर|शाम|रात)?"
)
PLACE_PATTERN = re.compile(
    r"(?im)^\s*([^\r\n,]+,\s*[^\r\n,]+,\s*(?:India|भारत))\s*$"
)
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _parse_overlay_timestamp(text: str) -> datetime | None:
    match = DATETIME_PATTERN.search(text)
    meridiem_map = {
        "पूर्वाह्न": "AM",
        "सकाळी": "AM",
        "सुबह": "AM",
        "अपराह्न": "PM",
        "दुपारी": "PM",
        "दोपहर": "PM",
        "शाम": "PM",
        "रात": "PM",
    }

    def combine(date_str: str, time_str: str, meridiem: str | None, date_formats: tuple[str, ...], tz_offset: str | None = None) -> datetime | None:
        normalized_meridiem = meridiem_map.get(meridiem, meridiem)
        normalized_time = (
            f"{time_str} {normalized_meridiem}"
            if normalized_meridiem and int(time_str[:2]) <= 12
            else time_str
        )
        timezone = datetime.strptime(tz_offset, "%z").tzinfo if tz_offset else INDIA_TIMEZONE
        for date_format in date_formats:
            for time_format in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"):
                try:
                    parsed = datetime.strptime(f"{date_str} {normalized_time}", f"{date_format} {time_format}")
                    return parsed.replace(tzinfo=timezone)
                except ValueError:
                    continue
        return None

    if match is not None:
        date_str, time_str, meridiem, tz_offset = match.groups()
        parsed = combine(date_str, time_str, meridiem, ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"), tz_offset)
        if parsed is not None:
            return parsed

    # Alternative GPS camera layouts place the time before the date or put
    # local time and date on separate lines, often using a written month.
    date_candidates: list[datetime] = []
    numeric_date = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)", text)
    if numeric_date:
        day, month, year = numeric_date.groups()
        date_format = "%d/%m/%Y" if len(year) == 4 else "%d/%m/%y"
        try:
            date_candidates.append(datetime.strptime(f"{day}/{month}/{year}", date_format))
        except ValueError:
            pass
    for pattern, date_format in NAMED_DATE_PATTERNS:
        if date_match := pattern.search(text):
            values = date_match.groups()
            month_value = values[1] if date_format.startswith("%d") else values[0]
            actual_format = date_format.replace("%B", "%b" if len(month_value) <= 3 else "%B")
            try:
                date_candidates.append(datetime.strptime(" ".join(values), actual_format))
            except ValueError:
                pass
    if not date_candidates:
        return None

    times = list(TIME_PATTERN.finditer(text))
    if not times:
        return None
    local_times = [
        item for item in times
        if re.search(r"local\s*[:：]?\s*$", text[max(0, item.start() - 20):item.start()], re.IGNORECASE)
    ]
    am_pm_times = [item for item in times if item.group(2)]
    selected_time = (local_times or am_pm_times or times)[0]
    time_str, meridiem = selected_time.groups()
    parsed_time = combine(date_candidates[0].strftime("%d/%m/%Y"), time_str, meridiem, ("%d/%m/%Y",))
    return parsed_time
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
    img = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    width, height = img.size

    # GPS camera overlays vary: some occupy the bottom third, others use a
    # full-width footer, and WhatsApp photos may include black bars. Read the
    # whole image plus two independently scaled bottom crops. Keeping the OCR
    # passes separate lets us detect disagreement instead of trusting the
    # first potentially misread date.
    full_text = pytesseract.image_to_string(img, lang="eng+hin+mar")
    text_passes = [full_text]
    for top_fraction, scale, psm in ((0.48, 3, 6),):
        crop = img.crop((0, int(height * top_fraction), width, height)).convert("L")
        crop = ImageOps.autocontrast(crop)
        crop = crop.resize(
            (max(1, crop.width * scale), max(1, crop.height * scale)),
            Image.Resampling.LANCZOS,
        )
        text_passes.append(pytesseract.image_to_string(
            crop,
            lang="eng+hin+mar",
            config=f"--psm {psm}",
        ))

    parsed_timestamps = [
        _parse_overlay_timestamp(part.translate(DEVANAGARI_DIGITS))
        for part in text_passes
    ]
    successful_reads = {candidate for candidate in parsed_timestamps if candidate is not None}
    if not successful_reads or len(successful_reads) > 1:
        # A third, narrower OCR pass is only needed when the normal passes
        # miss or disagree on date/time, keeping common-case latency low.
        crop = img.crop((0, int(height * 0.62), width, height)).convert("L")
        crop = ImageOps.autocontrast(crop)
        crop = crop.resize(
            (max(1, crop.width * 4), max(1, crop.height * 4)),
            Image.Resampling.LANCZOS,
        )
        text_passes.append(pytesseract.image_to_string(
            crop,
            lang="eng+hin+mar",
            config="--psm 11",
        ))

    raw_text = "\n".join(part for part in text_passes if part.strip())
    normalized_passes = [part.translate(DEVANAGARI_DIGITS) for part in text_passes]
    normalized_text = "\n".join(normalized_passes)

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

    timestamp_reads = [
        candidate
        for candidate in (_parse_overlay_timestamp(part) for part in normalized_passes)
        if candidate is not None
    ]
    timestamp_candidates = set(timestamp_reads)
    # A single successful read is useful; when OCR passes disagree, report it
    # as unreadable for manual review instead of asserting a possibly false
    # date mismatch.
    if len(timestamp_candidates) == 1:
        result.timestamp = next(iter(timestamp_candidates))
    elif timestamp_reads and max(timestamp_reads.count(value) for value in timestamp_candidates) >= 2:
        result.timestamp = max(timestamp_candidates, key=timestamp_reads.count)
    else:
        result.timestamp = None
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
