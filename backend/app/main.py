"""
FastAPI entry point.

Webhook design constraints:
  - The public webhook performs validation and durable Redis enqueue only; AI processing never runs inline.
  - Payload structure verified against a real captured event
    (see app/schemas.py for field-level notes).
"""
import logging
import hmac
from datetime import datetime, timezone, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.auth import (
    create_access_token,
    get_current_admin,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db.database import (
    AdminUser,
    CoordinatorRegistrationRequest,
    CoordinatorUpdateRequest,
    EmployeeRegistrationRequest,
    EmployeeUpdateRequest,
    ensure_indexes,
    get_admin_user,
    create_admin_user,
    get_db,
    migrate_legacy_reporting_hierarchy,
    list_admin_users,
    get_roster_by_employee_id,
    get_submissions_grouped,
    list_attendance,
    list_attendance_people,
    list_coordinators,
    list_employees,
    lookup_roster,
    register_coordinator,
    register_employee,
    resolve_flagged_submission,
    save_attendance_override,
    save_enrollment,
    update_admin_last_seen,
    update_coordinator,
    update_employee_details,
    create_manual_attendance,
    delete_attendance_submission,
    delete_coordinator_if_unassigned,
    delete_employee_without_attendance,
    register_webhook_event,
    mark_webhook_queued,
    normalize_date_str,
)
from app.schemas import InteraktWebhookPayload
from app.security import verify_webhook_signature
from app.services.face_match import enroll_embeddings
from app.redis_queue import ATTENDANCE_STREAM, ensure_stream_group, enqueue, get_redis
from app.services.attendance_grid import compute_employee_grid, daterange
from app.services.attendance_export_xlsx import (
    build_export_workbook,
    build_coordinator_details_workbook,
    build_participant_details_workbook,
)
from app.services.alert_formatting import format_issue_list, flag_reason_from_issues
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Attendance Verification Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=72)
    role: Literal["manual_team", "viewer"] = "viewer"

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, password: str) -> str:
        if len(password.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 UTF-8 bytes")
        return password


class ResolveRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    reason: str | None = None


class ManualAttendanceRequest(BaseModel):
    employee_id: str
    date: str  # "YYYY-MM-DD"
    reason: str  # required — the whole point of this endpoint is an auditable justification


class AttendanceOverrideRequest(BaseModel):
    employee_id: str
    date: str
    attendance_code: Literal["P", "L", "A", "AL", "HD", "WO", "H", "M", "F", "N/A"]
    reason: str | None = None


@app.on_event("startup")
async def on_startup():
    if settings.environment.lower() == "production":
        missing = []
        for name, value in {
            "JWT_SECRET_KEY": settings.jwt_secret_key,
            "INTERAKT_WEBHOOK_SECRET": settings.interakt_webhook_secret,
            "INTERAKT_API_KEY": settings.interakt_api_key,
        }.items():
            if not value or value in {"replace_me", "replace_with_a_long_random_secret", "replace_with_a_long_random_api_key"}:
                missing.append(name)
        if not missing:
            if "*" in settings.cors_origins:
                missing.append("CORS_ORIGINS must not contain *")
        if missing:
            raise RuntimeError("Production security configuration invalid: " + ", ".join(missing))
    """
    Ensures SQL Server indexes exist before the app serves traffic — this is
    what makes duplicate phone_number rejection and unique employee_id
    actually enforced. Previously this only happened if someone manually
    ran scripts/test_db_connection.py first, which was a real gap (caught
    via testing — see conversation history for details).
    """
    await ensure_indexes()
    if settings.environment.lower() == "testing":
        migrated = await migrate_legacy_reporting_hierarchy()
        if migrated:
            logger.info(
                "Migrated %d legacy participant(s) to direct coordinator reporting",
                migrated,
            )
    redis = get_redis()
    await ensure_stream_group(redis, ATTENDANCE_STREAM, "attendance-workers")
    await redis.close()
    database_label = "SQL Server"
    logger.info("%s indexes and Redis queue initialized", database_label)


@app.get("/health")
async def health():
    """Basic liveness endpoint; does not expose credentials or database details."""
    redis_ok = False
    try:
        redis = get_redis()
        redis_ok = bool(await redis.ping())
        await redis.close()
    except Exception:
        pass
    try:
        await get_db().command("ping")
        database_ok = True
    except Exception:
        database_ok = False
    status = "ok" if redis_ok and database_ok else "degraded"
    database_key = "mssql"
    return {"status": status, "redis": redis_ok, database_key: database_ok}


@app.post("/webhook/interakt")
async def interakt_webhook(
    request: Request,
    interakt_signature: str = Header(default=None, alias="Interakt-Signature"),
):
    """Validate, deduplicate, and durably enqueue an Interakt webhook.

    The HTTP request does no AI work. Redis Streams provides the durable handoff
    to the unified worker, while SQL Server stores the idempotency record.
    """
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, interakt_signature or ""):
        import hashlib

        received_signature = interakt_signature or ""
        received_hex = (
            received_signature[len("sha256="):]
            if received_signature.startswith("sha256=")
            else ""
        )

        expected_hex = hmac.new(
            key=settings.interakt_webhook_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        logger.warning(
            "Webhook HMAC mismatch | body_length=%d | received_length=%d | expected_length=%d | prefix_ok=%s",
            len(raw_body),
            len(received_hex),
            len(expected_hex),
            received_signature.startswith("sha256="),
        )

        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = InteraktWebhookPayload.model_validate_json(raw_body)
    except Exception as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
        return {"status": "received", "parsed": False}

    if payload.type != "message_received":
        return {"status": "ignored"}

    event_id = payload.data.message.id
    inserted = await register_webhook_event(event_id, payload.model_dump(mode="json"))

    # Duplicate events are safe to enqueue again: the worker claims the SQL
    # event atomically, so only one copy can execute the AI pipeline. Re-enqueue
    # is intentional because a prior delivery may have crashed after persistence.
    if not inserted:
        logger.info("Webhook event %s already exists; checking for unfinished work", event_id)

    sender_phone = payload.data.customer.phone_number
    if settings.admin_phone_number and sender_phone == settings.admin_phone_number:
        await update_admin_last_seen(datetime.now(timezone.utc))
        from app.db.database import complete_webhook_event
        await complete_webhook_event(event_id)
        return {"status": "admin_checkin", "duplicate": not inserted}

    redis = get_redis()
    try:
        await enqueue(redis, ATTENDANCE_STREAM, {
            "event_id": event_id,
            "payload": payload.model_dump(mode="json"),
            "attempt": 0,
        })
    finally:
        await redis.close()

    await mark_webhook_queued(event_id)
    return {"status": "received", "queued": True, "duplicate": not inserted}


@app.post("/auth/login")
async def login(request: LoginRequest):
    """
    CMS login — returns a JWT access token (valid for
    settings.jwt_expire_minutes). Pass it as `Authorization: Bearer <token>`
    Bootstrap super-admins are created via scripts/create_admin.py.
    Remaining accounts are created by authorized users in the CMS.
    """
    admin = await get_admin_user(request.username)
    unauthorized = HTTPException(status_code=401, detail="Incorrect username or password")
    if admin is None or not admin.is_active:
        raise unauthorized
    if not verify_password(request.password, admin.password_hash):
        raise unauthorized
    token = create_access_token(admin.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": admin.username,
        "role": admin.role,
    }


@app.get("/auth/me")
async def get_current_user_details(user: AdminUser = Depends(get_current_user)):
    """Return authenticated account metadata for frontend role handling."""
    return {"username": user.username, "role": user.role}


@app.get("/auth/users")
async def get_users(_: AdminUser = Depends(get_current_admin)):
    """List account metadata without exposing password hashes."""
    return {"users": await list_admin_users()}


@app.post("/auth/users", status_code=201)
async def create_user(
    request: UserRegistrationRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Create an account; only bootstrap super-admins may grant manual-team access."""
    if request.role == "manual_team" and admin.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Only a super-admin can create manual-team accounts",
        )
    try:
        user = await create_admin_user(
            request.username,
            hash_password(request.password),
            role=request.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"username": user.username, "role": user.role, "is_active": user.is_active}


@app.get("/config")
async def get_config(admin: AdminUser = Depends(get_current_user)):
    """
    Read-only — non-biometric thresholds currently enforced by the
    pipeline, so the frontend never hardcodes a value that could drift
    from what the backend actually checks.

    Deliberately EXCLUDES face-match confidence thresholds — per product
    decision, match confidence/percentage is never surfaced to the
    frontend anywhere. The actual thresholds still fully govern
    verification internally (see config.py, services/face_match.py) —
    this is purely about what the API exposes, not what's enforced.
    """
    return {
        "geofence_radius_meters": settings.geofence_radius_meters,
        "shift_window_start": settings.shift_window_start,
        "shift_window_end": settings.shift_window_end,
        "shift_grace_minutes": settings.shift_grace_minutes,
        "duplicate_hash_hamming_threshold": settings.duplicate_hash_hamming_threshold,
    }


@app.post("/coordinators")
async def create_coordinator(
    request: CoordinatorRegistrationRequest, admin: AdminUser = Depends(get_current_admin)
):
    """
    Register a new Project Coordinator. pc_id is auto-generated
    (PC001, PC002, ...). Field supervisors are linked to a PC via
    pc_id on their own roster record (set at registration or via PATCH).
    """
    try:
        coordinator = await register_coordinator(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return coordinator


@app.patch("/coordinators/{pc_id}")
async def patch_coordinator(
    pc_id: str, request: CoordinatorUpdateRequest, admin: AdminUser = Depends(get_current_admin)
):
    """Edit a coordinator's details, or deactivate them (is_active: false)."""
    try:
        updated = await update_coordinator(pc_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"No coordinator found with pc_id: {pc_id}")
    return updated


@app.delete("/coordinators/{pc_id}")
async def delete_coordinator(
    pc_id: str, admin: AdminUser = Depends(get_current_admin)
):
    """Permanently delete a coordinator only when no linked records exist."""
    linked_supervisors = await delete_coordinator_if_unassigned(pc_id)
    if linked_supervisors is None:
        raise HTTPException(status_code=404, detail=f"No coordinator found with pc_id: {pc_id}")
    if linked_supervisors:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete coordinator {pc_id}: {linked_supervisors} roster "
                "participant(s) are assigned to this coordinator. Reassign them first."
            ),
        )
    return {"status": "deleted"}


@app.get("/coordinators")
async def get_coordinators(
    pc_id: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_user),
):
    """
    List Project Coordinators, or look up one specific PC via pc_id.
    Example: GET /coordinators?pc_id=PC001 — returns a list with 0 or 1
    item (same pattern as GET /employees — filtering, not a distinct
    single-object endpoint with its own 404 behavior).
    search matches name or phone_number (case-insensitive substring).
    """
    coordinators, total = await list_coordinators(
        pc_id=pc_id, is_active=is_active, search=search, page=page, page_size=page_size
    )
    return {
        "count": len(coordinators), "total": total, "page": page, "page_size": page_size,
        "coordinators": coordinators,
    }


@app.get("/coordinators/export")
async def export_coordinator_details(
    search: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Export project coordinator details without attendance data."""
    coordinators, _ = await list_coordinators(
        search=search,
        page=1,
        page_size=100_000,
    )
    employees, _ = await list_employees(page=1, page_size=100_000)
    xlsx_bytes = build_coordinator_details_workbook(
        [coordinator.model_dump() for coordinator in coordinators],
        [employee.model_dump() for employee in employees],
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="project_coordinator_details.xlsx"'},
    )


@app.post("/employees")
async def create_employee(
    request: EmployeeRegistrationRequest, admin: AdminUser = Depends(get_current_admin)
):
    """
    Stage 1: HR registers a new employee with just phone number + name.
    employee_id is auto-generated and auto-incremented (EMP001, EMP002, ...).
    assigned_site, shift timing, and hierarchy fields (pc_id, area,
    designation) are left empty — set later via PATCH once decided.
    """
    try:
        employee = await register_employee(request)
    except ValueError as exc:
        # register_employee raises this for either a duplicate phone_number
        # OR an invalid pc_id — 409 (conflict) fits duplicates, but an
        # invalid pc_id is really a bad request (400), not a conflict.
        # Distinguish by message content since the function raises one
        # exception type for both cases.
        status = 400 if "pc_id" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
    return employee


@app.patch("/employees/{employee_id}")
async def patch_employee(
    employee_id: str, request: EmployeeUpdateRequest, admin: AdminUser = Depends(get_current_admin)
):
    """
    Stage 2: fill in assigned_site, shift timing, and/or hierarchy fields
    (pc_id, area, designation) once decided, or update phone_number (e.g.
    employee got a new number — see update_employee_details() docstring
    for the "takes effect immediately" caveat). Partial update — only
    fields actually provided in the request body change.
    """
    try:
        updated = await update_employee_details(employee_id, request)
    except ValueError as exc:
        # "already registered to a different employee" is a genuine
        # conflict (409), matching create_employee's convention — an
        # invalid pc_id is a plain bad request (400)
        status = 409 if "already" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"No employee found with employee_id: {employee_id}"
        )
    return updated


@app.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: str, admin: AdminUser = Depends(get_current_admin)
):
    """Delete a participant with no current attendance entries or child links."""
    linked_records = await delete_employee_without_attendance(employee_id)
    if linked_records is None:
        raise HTTPException(
            status_code=404, detail=f"No employee found with employee_id: {employee_id}"
        )
    attendance_count, override_count, child_count = linked_records
    if attendance_count or override_count or child_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete participant {employee_id}: {attendance_count} current "
                f"attendance record(s), {override_count} attendance override(s), and "
                f"{child_count} child assignment(s) remain. Superseded attempt history "
                "is retained and does not block deletion."
            ),
        )
    return {"status": "deleted"}


@app.get("/employees")
async def get_employees(
    pc_id: str | None = None,
    area: str | None = None,
    designation: str | None = None,
    role: str | None = None,
    parent_employee_id: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_user),
):
    """
    Roster listing for the CMS — all filters optional, combine any of them.
    Example: GET /employees?pc_id=PC001&is_active=true&page=2
    search matches name or phone_number (case-insensitive substring).
    """
    employees, total = await list_employees(
        pc_id=pc_id, area=area, designation=designation, role=role,
        parent_employee_id=parent_employee_id, is_active=is_active,
        search=search, page=page, page_size=page_size,
    )
    return {
        "count": len(employees), "total": total, "page": page, "page_size": page_size,
        "employees": employees,
    }


@app.get("/employees/export")
async def export_employee_details(
    pc_id: str | None = None,
    area: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """Export filtered participant details without attendance data."""
    employees, _ = await list_employees(
        pc_id=pc_id,
        area=area,
        is_active=is_active,
        search=search,
        page=1,
        page_size=100_000,
    )
    coordinators, _ = await list_coordinators(page_size=100_000)
    coordinator_names = {coordinator.pc_id: coordinator.name for coordinator in coordinators}
    xlsx_bytes = build_participant_details_workbook(
        [employee.model_dump() for employee in employees],
        coordinator_names,
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="attendance_participants.xlsx"'},
    )


@app.get("/attendance/grid")
async def get_attendance_grid(
    month: int,
    year: int,
    pc_id: str | None = None,
    role: Literal["PC", "FS", "LS", "LSS"] | None = None,
    admin: AdminUser = Depends(get_current_user),
):
    """Return monthly attendance for FS, LS, and LSS participants."""
    import calendar

    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    try:
        date_from = f"{year:04d}-{month:02d}-01"
        date_to = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        days = daterange(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    people, _ = await list_attendance_people(
        pc_id=pc_id, role=role, page=1, page_size=100_000
    )
    person_ids = [person.employee_id for person in people]
    submissions = await get_submissions_grouped(person_ids, date_from, date_to)

    rows = []
    for person in people:
        grid = compute_employee_grid(
            person.is_active,
            person.deactivated_at,
            submissions.get(person.employee_id, {}),
            days,
        )
        if grid is None:
            continue
        rows.append({
            "employee_id": person.employee_id,
            "name": person.name,
            "role": person.role,
            "pc_id": person.pc_id,
            "parent_employee_id": person.parent_employee_id,
            "area": person.area,
            "designation": person.designation,
            "is_active": person.is_active,
            "attendance": grid,
        })
    return {"month": month, "year": year, "days": days, "rows": rows}


@app.get("/attendance/people")
async def get_attendance_people(
    search: str | None = None,
    page_size: int = 20,
    admin: AdminUser = Depends(get_current_admin),
):
    """Search active FS, LS, and LSS participants for manual entry."""
    people, total = await list_attendance_people(
        is_active=True, search=search, page_size=min(max(page_size, 1), 100)
    )
    return {"count": len(people), "total": total, "people": people}


@app.patch("/attendance/override")
async def patch_attendance_override(
    request: AttendanceOverrideRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Audit and apply an administrator's monthly attendance-cell override."""
    try:
        return await save_attendance_override(
            request.employee_id,
            request.date,
            request.attendance_code,
            request.reason or "",
            admin.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/attendance")
async def get_attendance(
    employee_id: str | None = None,
    pc_id: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_user),
):
    """
    Attendance submission records for the CMS — filterable by employee,
    PC (all employees under that coordinator), verdict, and date range
    (date_from/date_to as YYYY-MM-DD).
    Example: GET /attendance?pc_id=PC001&date_from=2026-09-01&verdict=flagged
    search matches the submitting employee's name (case-insensitive).

    Each record includes issues_display: a human-readable version of the
    raw issues[] codes (which have runtime-computed suffixes like
    "geofence_fail_300m" — not safe to string-match directly). Use
    issues_display for UI text; issues[] if you need the raw codes.
    """
    records, total = await list_attendance(
        employee_id=employee_id, pc_id=pc_id, verdict=verdict,
        date_from=date_from, date_to=date_to, search=search,
        page=page, page_size=page_size,
    )
    from app.services.attendance_grid import marker_for_submission
    from app.services.shift_check import check_shift_window
    local_tz = ZoneInfo("Asia/Kolkata")
    for record in records:
        issues = record.get("issues") or []
        record["issues_display"] = format_issue_list(issues)
        for attempt in record.get("previous_flagged_attempts") or []:
            attempt["issues_display"] = format_issue_list(attempt.get("issues") or [])
        record["flag_reason"] = flag_reason_from_issues(issues) if record.get("verdict") == "flagged" else None
        photo_ts = record.get("photo_timestamp") or (record.get("overlay") or {}).get("timestamp")
        if photo_ts:
            try:
                capture = datetime.fromisoformat(str(photo_ts).replace("Z", "+00:00"))
                if capture.tzinfo is None:
                    capture = capture.replace(tzinfo=local_tz)
                capture = capture.astimezone(local_tz)
                record["check_in_at_ist"] = capture.isoformat()
                employee = await get_roster_by_employee_id(record["employee_id"]) if record.get("employee_id") else None
                if employee:
                    status, _ = check_shift_window(capture, employee.shift_start, employee.shift_end, employee.shift_grace_minutes, employee.role)
                    record["shift_status"] = status
            except (ValueError, TypeError):
                record["check_in_at_ist"] = None
        else:
            record["check_in_at_ist"] = None
        record["attendance_code"] = marker_for_submission(record)
        if record.get("entry_type") == "system" and record.get("attendance_status") == "absent":
            record["attendance_code"] = "A"
        if (
            record.get("entry_type") == "whatsapp"
            and record.get("verdict") == "verified"
            and record["check_in_at_ist"] is None
        ):
            record["attendance_code"] = "F"
        record["review_display"] = (
            "System absent (no image received)"
            if record.get("entry_type") == "system" and record.get("attendance_status") == "absent" else
            "Approved" if record.get("review_status") == "approved" else
            "Rejected" if record.get("review_status") == "rejected" else
            "Pending review" if record.get("verdict") == "flagged" else
            "Automatically verified" if record.get("verdict") == "verified" else
            "Not applicable"
        )
        location_match_status = record.get("location_match_status")
        location_match_level = record.get("location_match_level")
        if location_match_status == "disabled":
            record["geofence_display"] = "Location check disabled"
        elif location_match_status == "in_range":
            distance = record.get("geofence_distance_m", 0)
            radius = record.get("geofence_radius_meters", 0)
            record["geofence_display"] = f"Within range ({distance / 1000:.2f} km; limit {radius / 1000:g} km)"
        elif location_match_status in {"in_area", "out_of_area"}:
            level_label = "city" if location_match_level == "city" else "district"
            actual_location = (
                record.get("attendance_city")
                if location_match_level == "city"
                else record.get("attendance_district")
            )
            expected_location = (
                record.get("expected_city")
                if location_match_level == "city"
                else record.get("expected_district")
            )
            if location_match_status == "in_area":
                record["geofence_display"] = f"In {level_label}: {actual_location}"
            else:
                record["geofence_display"] = (
                    f"Out of {level_label}: {actual_location} "
                    f"(assigned: {expected_location})"
                )
        elif location_match_status == "unavailable":
            record["geofence_display"] = (
                "Outside range; city check unavailable — manual review"
                if record.get("location_check_method") == "range_then_city"
                else "City/district check unavailable"
            )
        else:
            radius = record.get("geofence_radius_meters")
            radius_display = (
                f"{radius / 1000:.2f}".rstrip("0").rstrip(".") + " km"
                if isinstance(radius, (int, float)) else None
            )
            if record.get("geofence_passed") is True:
                distance = record.get("geofence_distance_m")
                distance_display = (
                    f"{distance:.0f} m" if distance < 1000
                    else f"{distance / 1000:.2f} km"
                ) if isinstance(distance, (int, float)) else None
                record["geofence_display"] = (
                    f"Within range ({distance_display}; limit {radius_display})"
                    if distance_display and radius_display else
                    f"Within range ({distance_display})" if distance_display else "Within range"
                )
            elif record.get("geofence_passed") is False:
                distance = record.get("geofence_distance_m")
                distance_display = (
                    f"{distance:.0f} m" if distance < 1000
                    else f"{distance / 1000:.2f} km"
                ) if isinstance(distance, (int, float)) else None
                record["geofence_display"] = (
                    f"Outside range ({distance_display}; limit {radius_display})"
                    if distance_display and radius_display else
                    f"Outside range ({distance_display})" if distance_display
                    else "Outside range (distance unavailable)"
                )
            else:
                record["geofence_display"] = "Not verified (GPS/site missing)"
    override_keys = [
        {"employee_id": record["employee_id"], "attendance_date": record["attendance_date"]}
        for record in records
        if record.get("employee_id") and record.get("attendance_date")
    ]
    if override_keys:
        overrides_by_key = {}
        async for override in get_db().attendance_overrides.find({"$or": override_keys}):
            overrides_by_key[(override["employee_id"], override["attendance_date"])] = override["attendance_code"]
        for record in records:
            key = (record.get("employee_id"), record.get("attendance_date"))
            if key in overrides_by_key:
                record["attendance_code"] = overrides_by_key[key]
    return {
        "count": len(records), "total": total, "page": page, "page_size": page_size,
        "records": records,
    }


@app.delete("/attendance/{submission_id}")
async def delete_attendance(
    submission_id: str, admin: AdminUser = Depends(get_current_admin)
):
    """Permanently delete one attendance submission from the attendance records."""
    if not await delete_attendance_submission(submission_id):
        raise HTTPException(status_code=404, detail="Attendance record not found")
    return {"status": "deleted"}


@app.post("/attendance/manual")
async def create_manual_entry(
    request: ManualAttendanceRequest, admin: AdminUser = Depends(get_current_admin)
):
    """
    Deliberate backdoor for when the WhatsApp/AI pipeline fails (bad
    photo, dropped webhook, etc.) — NOT a general alternative to the
    normal flow. Always creates a verdict="verified" record (manual
    entries skip all automated checks by design). Shows as a distinct
    "M" marker in the Excel export, never conflated with an
    auto-verified "P".

    Blocked if a submission or saved status override already exists for
    this employee/date; a status override can be updated through the
    attendance status editor instead.
    """
    try:
        record = await create_manual_attendance(
            request.employee_id, request.date, request.reason, admin.username
        )
    except ValueError as exc:
        if "No employee found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc))
        norm_date = normalize_date_str(request.date)
        date_parts = norm_date.split("-")
        alternate_date = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0]}"
        database = get_db()
        existing_submission = await database.submissions.find_one({
            "employee_id": request.employee_id,
            "review_status": {"$ne": "superseded"},
            "$nor": [{"entry_type": "system", "attendance_status": "absent"}],
            "$or": [
                {"attendance_date": norm_date},
                {"received_at_utc": {"$regex": f"^{norm_date}"}},
                {"received_at_utc": {"$regex": f"^{alternate_date}"}},
            ],
        }, {"_id": 1})
        existing_override = await database.attendance_overrides.find_one(
            {"employee_id": request.employee_id, "attendance_date": norm_date},
            {"attendance_code": 1, "_id": 0},
        )
        if existing_submission is None and existing_override:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "status_override_exists",
                    "message": (
                        f"An attendance status was already changed for "
                        f"{request.employee_id} on {norm_date}. Use Change status "
                        "in the monthly attendance grid; deleting an attendance "
                        "record does not remove this saved status change."
                    ),
                    "attendance_code": existing_override.get("attendance_code", "P"),
                },
            )
        status = 409
        raise HTTPException(status_code=status, detail=str(exc))
    return record


@app.patch("/attendance/{submission_id}/resolve")
async def resolve_attendance(
    submission_id: str, request: ResolveRequest, admin: AdminUser = Depends(get_current_admin)
):
    """
    Admin resolves a flagged submission: "approved" -> counts as Present
    in the attendance export, "rejected" -> counts as Absent. Only works
    on submissions currently in "flagged" verdict state — already-verified
    or already-resolved records can't be re-resolved through this endpoint.
    """
    if request.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail='decision must be "approved" or "rejected"')
    updated = await resolve_flagged_submission(
        submission_id, request.decision, admin.username, request.reason
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="No flagged submission found with that ID (already resolved, verified, or doesn't exist)",
        )
    return updated


@app.get("/attendance/export")
async def export_attendance(
    month: int | None = None,
    year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    pc_id: str | None = None,
    employee_id: str | None = None,
    area: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Excel export with monthly attendance tabs for FS, LS, and LSS.

    Scope: EITHER month+year (e.g. ?month=9&year=2026) OR date_from+date_to
    (YYYY-MM-DD) — pass one pair, not both. Optionally narrow to one PC
    via pc_id; omit it for the full org.
    """
    if month is not None and year is not None:
        if date_from or date_to:
            raise HTTPException(status_code=400, detail="Pass either month+year OR date_from/date_to, not both")
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        date_from = f"{year:04d}-{month:02d}-01"
        date_to = f"{year:04d}-{month:02d}-{last_day:02d}"
    elif date_from is not None and date_to is not None:
        pass  # use as given
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either month+year or date_from+date_to",
        )

    days = daterange(date_from, date_to)

    # Keep coordinator names for employee hierarchy labels; PCs are not attendance participants.
    coordinators, _ = await list_coordinators(pc_id=pc_id, page_size=100_000)
    coordinators = [c.model_dump() for c in coordinators]
    employees, _ = await list_employees(pc_id=pc_id, area=area, page_size=100_000)
    employees = [e.model_dump() for e in employees]
    if employee_id is not None:
        employees = [
            employee for employee in employees
            if employee["employee_id"] == employee_id
        ]
        if not employees:
            raise HTTPException(
                status_code=404,
                detail=f"No attendance participant found with employee_id: {employee_id}",
            )

    if pc_id is not None and not coordinators:
        raise HTTPException(status_code=404, detail=f"No coordinator found with pc_id: {pc_id}")
    if employee_id is not None or (area is not None and pc_id is None):
        included_pc_ids = {employee.get("pc_id") for employee in employees}
        coordinators = [
            coordinator for coordinator in coordinators
            if coordinator.get("pc_id") in included_pc_ids
        ]

    participants = employees
    employee_ids = [person["employee_id"] for person in participants]
    submissions_by_employee = await get_submissions_grouped(employee_ids, date_from, date_to)

    grids = {}
    for person in participants:
        grids[person["employee_id"]] = compute_employee_grid(
            person.get("is_active", True),
            person.get("deactivated_at"),
            submissions_by_employee.get(person["employee_id"], {}),
            days,
        )

    xlsx_bytes = build_export_workbook(coordinators, employees, grids, days)

    filename = f"attendance_{date_from}_to_{date_to}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/enroll-face")
async def enroll_face(
    employee_id: str = Form(...),
    photos: list[UploadFile] = File(...),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    HR/admin-facing enrollment endpoint — uploads 1 to 5 reference photos
    for an employee, used later by face-identity verification. 5 is
    recommended for best accuracy (see our design discussion on why), but
    fewer is accepted — useful for early testing or partial rollout.

    NOTE: does not require live WhatsApp traffic to test — call directly
    via curl/Postman with employee_id (form field) and 1-5 image files
    (multipart, field name "photos", repeated).

    IMPORTANT: per our design discussion, do not call this in production
    until biometric consent (DPDP) is confirmed collected for the employee
    being enrolled — this endpoint does not itself verify consent.
    """
    if not (1 <= len(photos) <= 5):
        raise HTTPException(
            status_code=400,
            detail=f"Between 1 and 5 reference photos required, got {len(photos)}",
        )

    roster_entry = await get_roster_by_employee_id(employee_id)
    if roster_entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No roster entry found for employee_id: {employee_id}",
        )
    if roster_entry.role == "PC":
        raise HTTPException(
            status_code=422,
            detail="Project coordinators are not attendance participants",
        )

    image_bytes_list = [await photo.read() for photo in photos]
    embeddings = enroll_embeddings(image_bytes_list)

    if len(embeddings) == 0:
        raise HTTPException(
            status_code=422,
            detail="No face detected in any of the 5 photos — enrollment failed",
        )
    if len(embeddings) < 5:
        logger.warning(
            "Only %d reference photo(s) with a detectable face for employee %s — "
            "fewer than the recommended 5, matching may be less robust to angle/lighting variance",
            len(embeddings), employee_id,
        )

    await save_enrollment(employee_id, embeddings)

    return {
        "status": "enrolled",
        "employee_id": employee_id,
        "name": roster_entry.name,
        "embeddings_stored": len(embeddings),
    }


class LocationCoordinates(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    long: float = Field(ge=-180, le=180, allow_inf_nan=False)


@app.post("/sites/resolve-location")
async def resolve_site_location(coordinates: LocationCoordinates, admin: AdminUser = Depends(get_current_admin)):
    from app.services.city_lookup import resolve_city
    return await resolve_city(coordinates.lat, coordinates.long)


@app.post("/sites/extract-photo")
async def extract_site_photo(file: UploadFile = File(...), admin: AdminUser = Depends(get_current_admin)):
    """Extract GPS camera overlay; admin must confirm coordinates before saving."""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG or WebP image")
    data = await file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Maximum image size is 8 MB")
    from app.services.ocr import extract_overlay_data
    try:
        result = extract_overlay_data(data)
    except Exception:
        logger.exception("GPS image OCR failed")
        raise HTTPException(status_code=422, detail="Could not read GPS image")
    if result.latitude is None or result.longitude is None:
        raise HTTPException(status_code=422, detail="GPS coordinates not found; enter manually")
    if not (-90 <= result.latitude <= 90 and -180 <= result.longitude <= 180):
        raise HTTPException(status_code=422, detail="Invalid GPS coordinates")
    from app.services.city_lookup import resolve_city
    area = await resolve_city(result.latitude, result.longitude)
    return {
        "name": area.get("place") or result.place or "GPS photo location",
        "place": area.get("place") or result.place,
        "city": area.get("city"),
        "district": area.get("district"),
        "district_id": area.get("district_id"),
        "dataset_id": area.get("dataset_id"),
        "status": area.get("status"),
        "match_level": "city",
        "lat": result.latitude,
        "long": result.longitude,
        "requires_confirmation": True,
    }
