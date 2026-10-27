"""
SQL Server-backed application models, roster lookup, and attendance operations.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.services.attendance_grid import marker_for_submission
from app.services.shift_check import role_shift_defaults

logger = logging.getLogger("db")

def get_db():
    from app.db.mssql import get_db as get_mssql_db

    return get_mssql_db()


def normalize_date_str(val: str | None) -> str:
    """Normalizes any date string (ISO YYYY-MM-DD, DD/MM/YYYY, or DD-MM-YYYY) to YYYY-MM-DD."""
    if not val:
        return ""
    val = str(val).strip()

    if re.match(r"^\d{4}-\d{2}-\d{2}", val):
        return val[:10]

    match = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{4})", val)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"

    return val[:10]


class AssignedSite(BaseModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    long: float = Field(ge=-180, le=180)
    city: str | None = None
    district: str | None = None
    district_id: str | None = None
    dataset_id: str | None = None
    match_level: Literal["city", "district"] = "city"


class Coordinator(BaseModel):
    pc_id: str
    name: str
    phone_number: str | None = None
    is_active: bool = True
    deactivated_at: str | None = None
    role: Literal["PC"] = "PC"


class CoordinatorRegistrationRequest(BaseModel):
    name: str
    phone_number: str | None = None


class CoordinatorUpdateRequest(BaseModel):
    name: str | None = None
    phone_number: str | None = None
    is_active: bool | None = None


class RosterEntry(BaseModel):
    phone_number: str
    employee_id: str
    name: str
    is_active: bool = True
    deactivated_at: str | None = None
    role: Literal["PC", "FS", "LS", "LSS"] = "FS"
    pc_id: str | None = None
    parent_employee_id: str | None = None
    area: str | None = None
    designation: str | None = None
    location_check_enabled: bool = True
    assigned_site: AssignedSite | None = None
    geofence_radius_km: float = Field(default=8.0, gt=0, allow_inf_nan=False)
    shift_start: str | None = None
    shift_end: str | None = None
    shift_grace_minutes: int | None = None


class EmployeeRegistrationRequest(BaseModel):
    phone_number: str
    name: str
    role: Literal["FS", "LS", "LSS"] = "FS"
    pc_id: str | None = None
    parent_employee_id: str | None = None
    area: str | None = None
    designation: str | None = None
    location_check_enabled: bool = True
    assigned_site: AssignedSite | None = None
    geofence_radius_km: float = Field(default=8.0, gt=0, allow_inf_nan=False)
    shift_start: str | None = None
    shift_end: str | None = None
    shift_grace_minutes: int | None = None


class EmployeeUpdateRequest(BaseModel):
    phone_number: Optional[str] = None
    role: Optional[Literal["FS", "LS", "LSS"]] = None
    pc_id: Optional[str] = None
    parent_employee_id: Optional[str] = None
    area: Optional[str] = None
    designation: Optional[str] = None
    location_check_enabled: bool = True
    assigned_site: Optional[AssignedSite] = None
    geofence_radius_km: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    shift_grace_minutes: Optional[int] = None
    is_active: Optional[bool] = None


def normalize_phone(value: str | None) -> str:
    """Canonical Indian phone number for WhatsApp/roster matching."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return digits


def _phone_number_variants(value: str) -> list[str]:
    normalized = normalize_phone(value)
    variants = [normalized, "+" + normalized]
    if normalized.startswith("91") and len(normalized) == 12:
        variants.extend([normalized[2:], "0" + normalized[2:]])
    return variants


async def _phone_number_is_registered(
    phone_number: str,
    *,
    exclude_employee_id: str | None = None,
    exclude_pc_id: str | None = None,
) -> bool:
    variants = _phone_number_variants(phone_number)
    db = get_db()

    roster_query = {"phone_number": {"$in": variants}}
    if exclude_employee_id is not None:
        roster_query["employee_id"] = {"$ne": exclude_employee_id}
    if await db.roster.find_one(roster_query, {"_id": 1}):
        return True

    coordinator_query = {"phone_number": {"$in": variants}}
    if exclude_pc_id is not None:
        coordinator_query["pc_id"] = {"$ne": exclude_pc_id}
    return await db.coordinators.find_one(coordinator_query, {"_id": 1}) is not None


async def lookup_roster(phone_number: str) -> RosterEntry | None:
    db = get_db()
    normalized = normalize_phone(phone_number)
    variants = [normalized, "+" + normalized]
    if normalized.startswith("91") and len(normalized) == 12:
        variants.extend([normalized[2:], "0" + normalized[2:]])
    doc = await db.roster.find_one({"phone_number": normalized})
    if doc is None:
        # Backward compatibility with previously stored +91 / local numbers.
        doc = await db.roster.find_one({"phone_number": {"$in": variants}})
    if doc is None:
        doc = await db.coordinators.find_one({"phone_number": {"$in": variants}})
        if doc is not None:
            return RosterEntry(
                employee_id=doc["pc_id"],
                phone_number=doc.get("phone_number") or normalized,
                name=doc["name"],
                is_active=doc.get("is_active", True),
                deactivated_at=doc.get("deactivated_at"),
                role="PC",
                pc_id=doc["pc_id"],
            )
        logger.warning("No roster entry found for phone number: %s", normalized)
        return None
    return RosterEntry(**doc)


async def get_roster_by_employee_id(employee_id: str) -> RosterEntry | None:
    db = get_db()
    doc = await db.roster.find_one({"employee_id": employee_id})
    if doc is None:
        pc = await db.coordinators.find_one({"pc_id": employee_id})
        if pc is None:
            return None
        return RosterEntry(
            employee_id=pc["pc_id"],
            phone_number=pc.get("phone_number") or "",
            name=pc["name"],
            is_active=pc.get("is_active", True),
            deactivated_at=pc.get("deactivated_at"),
            role="PC",
            pc_id=pc["pc_id"],
        )
    return RosterEntry(**doc)


async def ensure_indexes() -> None:
    from app.db.mssql import ensure_indexes as ensure_mssql_indexes

    await ensure_mssql_indexes()


async def migrate_legacy_reporting_hierarchy() -> int:
    """Resolve legacy supervisor chains to direct project-coordinator assignments."""
    db = get_db()
    cursor = db.roster.find({
        "role": {"$in": ["FS", "LS", "LSS"]},
        "parent_employee_id": {"$ne": None},
    })
    migrated = 0
    async for employee in cursor:
        coordinator_id = employee.get("pc_id")
        coordinator = (
            await get_coordinator_by_id(coordinator_id)
            if coordinator_id
            else None
        )
        if coordinator is None:
            parent_id = employee.get("parent_employee_id")
            visited = {employee.get("employee_id")}
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = await get_roster_by_employee_id(parent_id)
                if parent is None:
                    coordinator = await get_coordinator_by_id(parent_id)
                    if coordinator is not None:
                        coordinator_id = parent_id
                    break
                if parent.pc_id:
                    coordinator = await get_coordinator_by_id(parent.pc_id)
                    if coordinator is not None:
                        coordinator_id = parent.pc_id
                        break
                parent_id = parent.parent_employee_id

        if coordinator is None or not coordinator_id:
            logger.warning(
                "Leaving legacy participant %s unchanged: its project coordinator "
                "could not be resolved",
                employee.get("employee_id", "unknown"),
            )
            continue
        await db.roster.update_one(
            {
                "employee_id": employee["employee_id"],
                "parent_employee_id": employee["parent_employee_id"],
            },
            {"$set": {"pc_id": coordinator_id, "parent_employee_id": None}},
        )
        migrated += 1
    return migrated


async def get_next_pc_id() -> str:
    db = get_db()
    result = await db.counters.find_one_and_update(
        {"_id": "pc_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return f"PC{result['seq']:03d}"


async def register_coordinator(request: CoordinatorRegistrationRequest) -> Coordinator:
    db = get_db()
    if request.phone_number and await _phone_number_is_registered(request.phone_number):
        raise ValueError("phone_number is already registered to another attendance participant")
    pc_id = await get_next_pc_id()
    doc = {
        "pc_id": pc_id,
        "name": request.name,
        "phone_number": request.phone_number,
        "is_active": True,
    }
    await db.coordinators.insert_one(doc)
    return Coordinator(**doc)


async def get_coordinator_by_id(pc_id: str) -> Coordinator | None:
    db = get_db()
    doc = await db.coordinators.find_one({"pc_id": pc_id})
    if doc is None:
        return None
    return Coordinator(**doc)


async def list_coordinators(
    pc_id: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Coordinator], int]:
    query = {}
    if pc_id is not None:
        query["pc_id"] = pc_id
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone_number": {"$regex": search, "$options": "i"}},
        ]
    db = get_db()
    total = await db.coordinators.count_documents(query)
    skip = (page - 1) * page_size
    entries = []
    async for doc in db.coordinators.find(query).skip(skip).limit(page_size):
        entries.append(Coordinator(**doc))
    return entries, total


async def update_coordinator(
    pc_id: str, updates: CoordinatorUpdateRequest
) -> Coordinator | None:
    db = get_db()
    set_fields = updates.model_dump(exclude_unset=True)

    current = await get_coordinator_by_id(pc_id) if "phone_number" in set_fields else None
    if (
        current is not None
        and set_fields["phone_number"]
        and normalize_phone(set_fields["phone_number"]) != normalize_phone(current.phone_number)
        and await _phone_number_is_registered(
            set_fields["phone_number"], exclude_pc_id=pc_id
        )
    ):
        raise ValueError("phone_number is already registered to another attendance participant")

    if "is_active" in set_fields:
        current = current or await get_coordinator_by_id(pc_id)
        if current is not None and current.is_active != set_fields["is_active"]:
            if set_fields["is_active"] is False:
                set_fields["deactivated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else:
                set_fields["deactivated_at"] = None

    if not set_fields:
        return await get_coordinator_by_id(pc_id)
    doc = await db.coordinators.find_one_and_update(
        {"pc_id": pc_id},
        {"$set": set_fields},
        return_document=True,
    )
    if doc is None:
        return None
    return Coordinator(**doc)


async def delete_coordinator_if_unassigned(pc_id: str) -> int | None:
    """Delete a coordinator only when no roster entries are assigned to it.

    Historical attendance records are retained for audit and do not block
    removing a coordinator profile, since coordinators are not participants.
    Returns the number of linked roster entries, or None if not found.
    """
    db = get_db()
    if await db.coordinators.find_one({"pc_id": pc_id}, {"_id": 1}) is None:
        return None
    linked_supervisors = await db.roster.count_documents({"pc_id": pc_id})
    if linked_supervisors:
        return linked_supervisors

    result = await db.coordinators.delete_one({"pc_id": pc_id})
    return 0 if result.deleted_count == 1 else None


async def get_next_employee_id() -> str:
    db = get_db()
    result = await db.counters.find_one_and_update(
        {"_id": "employee_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = result["seq"]
    return f"EMP{seq:03d}"


async def _validated_hierarchy(
    role: str,
    pc_id: str | None,
    parent_employee_id: str | None,
) -> tuple[str | None, str | None]:
    if parent_employee_id:
        raise ValueError("Attendance participants must report directly to a project coordinator")
    if role not in ("FS", "LS", "LSS"):
        raise ValueError(f"Unsupported attendance participant role: {role}")
    if not pc_id:
        raise ValueError(f"{role} must be assigned to a project coordinator")
    if await get_coordinator_by_id(pc_id) is None:
        raise ValueError(f"pc_id {pc_id} does not match any registered coordinator")
    return pc_id, None


async def register_employee(request: EmployeeRegistrationRequest) -> RosterEntry:
    pc_id, parent_employee_id = await _validated_hierarchy(
        request.role, request.pc_id, request.parent_employee_id
    )

    db = get_db()
    if await _phone_number_is_registered(request.phone_number):
        raise ValueError("phone_number is already registered to another attendance participant")
    employee_id = await get_next_employee_id()
    doc = {
        "employee_id": employee_id,
        "phone_number": request.phone_number,
        "name": request.name,
        "is_active": True,
        "role": request.role,
        "pc_id": pc_id,
        "parent_employee_id": parent_employee_id,
        "area": request.area,
        "designation": request.designation,
        "location_check_enabled": request.location_check_enabled if request.role == "FS" else True,
        "assigned_site": request.assigned_site.model_dump() if request.assigned_site else None,
        "geofence_radius_km": request.geofence_radius_km,
        "shift_start": request.shift_start if request.shift_start is not None else role_shift_defaults(request.role)["shift_start"],
        "shift_end": request.shift_end if request.shift_end is not None else role_shift_defaults(request.role)["shift_end"],
        "shift_grace_minutes": request.shift_grace_minutes if request.shift_grace_minutes is not None else role_shift_defaults(request.role)["shift_grace_minutes"],
    }
    try:
        await db.roster.insert_one(doc)
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise ValueError(f"phone_number {request.phone_number} is already registered")
        raise
    return RosterEntry(**doc)


async def update_employee_details(
    employee_id: str, updates: EmployeeUpdateRequest
) -> Optional[RosterEntry]:
    db = get_db()
    current = await get_roster_by_employee_id(employee_id)
    if current is None:
        return None
    set_fields = {
        k: (v.model_dump() if isinstance(v, AssignedSite) else v)
        for k, v in updates.model_dump(exclude_unset=True).items()
    }
    if (
        set_fields.get("phone_number")
        and normalize_phone(set_fields["phone_number"]) != normalize_phone(current.phone_number)
        and await _phone_number_is_registered(
            set_fields["phone_number"], exclude_employee_id=employee_id
        )
    ):
        raise ValueError("phone_number is already registered to another attendance participant")
    role = set_fields.get("role", current.role)
    if role != "FS" and ("location_check_enabled" in set_fields or role != current.role):
        set_fields["location_check_enabled"] = True
    for key, default in role_shift_defaults(role).items():
        if (role != current.role and key not in set_fields) or (key in set_fields and set_fields[key] in (None, "")):
            set_fields[key] = default
    pc_id = set_fields.get("pc_id", current.pc_id)
    parent_employee_id = set_fields.get(
        "parent_employee_id",
        None if role != current.role else current.parent_employee_id,
    )
    if {"role", "pc_id", "parent_employee_id"} & set_fields.keys():
        if current.role == "FS" and (role != "FS" or pc_id != current.pc_id):
            local_supervisor_count = await db.roster.count_documents(
                {"role": "LS", "parent_employee_id": employee_id}
            )
            if local_supervisor_count:
                raise ValueError(
                    f"Cannot change the role or coordinator for {employee_id} while "
                    f"{local_supervisor_count} local supervisor(s) report to them; "
                    "reassign those local supervisors first"
                )
        pc_id, parent_employee_id = await _validated_hierarchy(
            role, pc_id, parent_employee_id
        )
        set_fields["pc_id"] = pc_id
        set_fields["parent_employee_id"] = parent_employee_id

    if "is_active" in set_fields:
        if current.is_active != set_fields["is_active"]:
            if set_fields["is_active"] is False:
                set_fields["deactivated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else:
                set_fields["deactivated_at"] = None

    if not set_fields:
        return current

    try:
        doc = await db.roster.find_one_and_update(
            {"employee_id": employee_id},
            {"$set": set_fields},
            return_document=True,
        )
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise ValueError(
                f"phone_number {set_fields.get('phone_number')} is already registered to a different employee"
            )
        raise
    if doc is None:
        return None
    return RosterEntry(**doc)


async def delete_employee_without_attendance(
    employee_id: str,
) -> tuple[int, int, int] | None:
    """Delete a participant only when no current attendance or child links exist.

    Superseded submissions are kept as audit history and do not block deletion.
    Returns counts of current attendance, overrides and child assignments, or
    None if the participant does not exist.
    """
    db = get_db()
    if await db.roster.find_one({"employee_id": employee_id}, {"_id": 1}) is None:
        return None

    attendance_count = await db.submissions.count_documents({
        "employee_id": employee_id,
        "review_status": {"$ne": "superseded"},
    })
    override_count = await db.attendance_overrides.count_documents(
        {"employee_id": employee_id}
    )
    child_count = await db.roster.count_documents(
        {"parent_employee_id": employee_id}
    )
    if attendance_count or override_count or child_count:
        return attendance_count, override_count, child_count

    result = await db.roster.delete_one({"employee_id": employee_id})
    if result.deleted_count != 1:
        return None

    await db.face_embeddings.delete_one({"employee_id": employee_id})
    return 0, 0, 0


async def save_enrollment(employee_id: str, embeddings: list[list[float]]) -> None:
    db = get_db()
    await db.face_embeddings.update_one(
        {"employee_id": employee_id},
        {"$set": {"employee_id": employee_id, "embeddings": embeddings}},
        upsert=True,
    )


async def get_enrollment(employee_id: str) -> list[list[float]]:
    db = get_db()
    doc = await db.face_embeddings.find_one({"employee_id": employee_id})
    if doc is None:
        return []
    return doc.get("embeddings", [])


async def list_employees_by_pc(pc_id: str) -> list[RosterEntry]:
    db = get_db()
    entries = []
    async for doc in db.roster.find({"pc_id": pc_id}):
        entries.append(RosterEntry(**doc))
    return entries


async def list_attendance_people(
    pc_id: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RosterEntry], int]:
    if role == "PC":
        return [], 0

    employees, employee_total = await list_employees(
        pc_id=pc_id, role=role, is_active=is_active, search=search,
        page=1, page_size=100_000
    )
    employees = [person for person in employees if person.role != "PC"]
    people = employees
    people.sort(key=lambda person: person.name.casefold())
    start = (page - 1) * page_size
    return people[start:start + page_size], len(people)


async def list_employees(
    pc_id: str | None = None,
    area: str | None = None,
    designation: str | None = None,
    role: str | None = None,
    parent_employee_id: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RosterEntry], int]:
    query = {}
    if pc_id is not None:
        query["pc_id"] = pc_id
    if area is not None:
        query["area"] = area
    if designation is not None:
        query["designation"] = designation
    if role is not None:
        query["role"] = role
    if parent_employee_id is not None:
        query["parent_employee_id"] = parent_employee_id
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone_number": {"$regex": search, "$options": "i"}},
        ]

    db = get_db()
    total = await db.roster.count_documents(query)
    skip = (page - 1) * page_size
    entries = []
    async for doc in db.roster.find(query).skip(skip).limit(page_size):
        entries.append(RosterEntry(**doc))
    return entries, total


async def get_admin_last_seen():
    db = get_db()
    doc = await db.admin_state.find_one({"_id": "admin"})
    if doc is None:
        return None
    return doc.get("last_message_utc")


async def list_attendance(
    employee_id: str | None = None,
    pc_id: str | None = None,
    verdict: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    db = get_db()
    query: dict = {
        "review_status": {"$ne": "superseded"},
        "person_role": {"$ne": "PC"},
    }
    coordinator_ids = [
        coordinator.pc_id
        for coordinator in (await list_coordinators(page_size=100_000))[0]
    ]
    if coordinator_ids:
        query["$nor"] = [{"employee_id": {"$in": coordinator_ids}}]

    if employee_id is not None:
        query["employee_id"] = employee_id
    if verdict is not None:
        query["verdict"] = verdict

    if date_from is not None or date_to is not None:
        date_conditions = []
        if date_from is not None:
            norm_from = normalize_date_str(date_from)
            date_conditions.append({
                "$or": [
                    {"attendance_date": {"$gte": norm_from}},
                    {"received_at_utc": {"$gte": norm_from}},
                ]
            })
        if date_to is not None:
            norm_to = normalize_date_str(date_to)
            date_conditions.append({
                "$or": [
                    {"attendance_date": {"$lte": norm_to}},
                    {"received_at_utc": {"$lte": norm_to + "T23:59:59.999999"}},
                ]
            })
        if len(date_conditions) == 1:
            query.update(date_conditions[0])
        elif len(date_conditions) > 1:
            query["$and"] = date_conditions

    if pc_id is not None:
        employee_ids = [pc_id]
        employee_ids.extend(e.employee_id for e in await list_employees_by_pc(pc_id))
        query["employee_id"] = {"$in": employee_ids}

    if search:
        matching, _ = await list_employees(search=search, page=1, page_size=10_000)
        matching_pcs, _ = await list_coordinators(search=search, page_size=10_000)
        matched_ids = [e.employee_id for e in matching]
        matched_ids.extend(pc.pc_id for pc in matching_pcs)
        if "employee_id" in query and isinstance(query["employee_id"], dict):
            existing_ids = set(query["employee_id"]["$in"])
            query["employee_id"] = {"$in": list(existing_ids & set(matched_ids))}
        else:
            query["employee_id"] = {"$in": matched_ids}

    total = await db.submissions.count_documents(query)
    skip = (page - 1) * page_size
    results = []
    async for doc in (
        db.submissions.find(query)
        .sort([("received_at_utc", -1), ("_id", -1)])
        .skip(skip)
        .limit(page_size)
    ):
        doc["_id"] = str(doc["_id"])
        if not doc.get("attendance_date"):
            doc["attendance_date"] = normalize_date_str(doc.get("received_at_utc"))
        results.append(doc)
    return results, total


async def delete_attendance_submission(submission_id: str) -> bool:
    from app.db.mssql import delete_attendance_submission_transactional

    return await delete_attendance_submission_transactional(submission_id)


async def has_submission_today(
    employee_id: str, date_str: str, *, include_system_absences: bool = True
) -> bool:
    """Checks whether this employee already has an attendance record for the date."""
    db = get_db()
    norm_date = normalize_date_str(date_str)
    parts = norm_date.split("-")
    alt_date = f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else norm_date
    query = {
        "employee_id": employee_id,
        "review_status": {"$ne": "superseded"},
        "$or": [
            {"attendance_date": norm_date},
            {"received_at_utc": {"$regex": f"^{norm_date}"}},
            {"received_at_utc": {"$regex": f"^{alt_date}"}},
        ],
    }
    if not include_system_absences:
        query["$nor"] = [
            {"entry_type": "system", "attendance_status": "absent"}
        ]
    existing = await db.submissions.find_one(query)
    if existing is not None:
        return True
    return await db.attendance_overrides.find_one(
        {"employee_id": employee_id, "attendance_date": norm_date},
        {"_id": 1},
    ) is not None


async def get_retryable_submission_today(
    employee_id: str, date_str: str
) -> dict | None:
    """Returns the latest unresolved flagged WhatsApp attempt, if it can be retried."""
    norm_date = normalize_date_str(date_str)
    parts = norm_date.split("-")
    alt_date = f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else norm_date

    db = get_db()
    if await db.attendance_overrides.find_one(
        {"employee_id": employee_id, "attendance_date": norm_date},
        {"_id": 1},
    ):
        return None

    submission = await db.submissions.find_one(
        {
            "employee_id": employee_id,
            "review_status": {"$ne": "superseded"},
            "$nor": [{"entry_type": "system", "attendance_status": "absent"}],
            "$or": [
                {"attendance_date": norm_date},
                {"received_at_utc": {"$regex": f"^{norm_date}"}},
                {"received_at_utc": {"$regex": f"^{alt_date}"}},
            ],
        },
        sort=[("received_at_utc", -1), ("_id", -1)],
    )
    if (
        submission
        and submission.get("entry_type") == "whatsapp"
        and submission.get("verdict") == "flagged"
        and submission.get("review_status") == "pending"
    ):
        return submission
    return None


async def delete_system_absences_today(employee_id: str, date_str: str) -> None:
    """Remove an auto-absence if a real attendance record arrives later that day."""
    await get_db().submissions.delete_many({
        "employee_id": employee_id,
        "attendance_date": normalize_date_str(date_str),
        "entry_type": "system",
        "attendance_status": "absent",
    })


async def resolve_flagged_submission(
    submission_id: str, decision: str, resolved_by: str, reason: str | None = None
):
    from app.db.identifiers import parse_record_id

    if decision not in ("approved", "rejected"):
        raise ValueError('decision must be "approved" or "rejected"')

    db = get_db()
    try:
        obj_id = parse_record_id(submission_id)
    except Exception:
        return None

    doc = await db.submissions.find_one({"_id": obj_id})
    if doc is None or doc.get("verdict") != "flagged":
        return None

    attendance_status = "present" if decision == "approved" else "absent"

    await db.submissions.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "review_status": decision,
                "attendance_status": attendance_status,
                "resolved_by": resolved_by,
                "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
                "resolution_reason": reason,
            }
        },
    )
    updated = await db.submissions.find_one({"_id": obj_id})
    updated["_id"] = str(updated["_id"])
    return updated


async def get_submissions_grouped(
    employee_ids: list[str],
    date_from: str,
    date_to: str,
) -> dict[str, dict[str, dict]]:
    """Selects one daily attendance outcome per employee for the Excel grid."""
    db = get_db()
    result: dict[str, dict[str, dict]] = {emp_id: {} for emp_id in employee_ids}

    if not employee_ids:
        return result

    norm_from = normalize_date_str(date_from)
    norm_to = normalize_date_str(date_to)

    cursor = db.submissions.find({"employee_id": {"$in": employee_ids}})

    def rank(sub: dict) -> tuple[int, str, str]:
        verdict = sub.get("verdict")
        review = sub.get("review_status")
        entry_type = sub.get("entry_type")
        shift = sub.get("shift_status")
        timestamp = str(sub.get("received_at_utc") or "")
        record_id = str(sub.get("_id") or "")

        if entry_type == "manual":
            priority = 6
        elif verdict == "verified":
            priority = 5
        elif verdict == "flagged" and review == "approved":
            priority = 4
        elif verdict == "flagged" and review == "rejected":
            priority = 3
        elif verdict == "inactive_account":
            priority = 2
        elif verdict == "flagged":
            priority = 1
        else:
            priority = 0

        on_time_pref = 1 if shift != "late" else 0
        return (priority * 10 + on_time_pref, timestamp, record_id)

    async for doc in cursor:
        emp_id = doc.get("employee_id")
        if emp_id not in result:
            continue

        raw_date = doc.get("attendance_date") or doc.get("received_at_utc")
        day = normalize_date_str(raw_date)

        if not (norm_from <= day <= norm_to):
            continue

        current = result[emp_id].get(day)
        if current is None or rank(doc) > rank(current):
            result[emp_id][day] = doc

    overrides = db.attendance_overrides.find({
        "employee_id": {"$in": employee_ids},
        "attendance_date": {"$gte": norm_from, "$lte": norm_to},
    })
    async for override in overrides:
        emp_id = override["employee_id"]
        day = override["attendance_date"]
        result[emp_id][day] = {
            "employee_id": emp_id,
            "attendance_date": day,
            "attendance_code": override["attendance_code"],
            "entry_type": "override",
        }

    return result


async def create_manual_attendance(
    employee_id: str, date: str, reason: str, created_by: str
) -> dict:
    roster_entry = await get_roster_by_employee_id(employee_id)
    if roster_entry is None:
        raise ValueError(f"No employee found with employee_id: {employee_id}")
    if roster_entry.role == "PC":
        raise ValueError("Project coordinators are not attendance participants")

    norm_date = normalize_date_str(date)
    if await has_submission_today(
        employee_id, norm_date, include_system_absences=False
    ):
        raise ValueError(
            f"A submission already exists for {employee_id} on {norm_date} — "
            f"use PATCH /attendance/{{id}}/resolve on the existing record instead"
        )

    db = get_db()
    doc = {
        "employee_id": employee_id,
        "employee_name": roster_entry.name,
        "person_role": roster_entry.role,
        "pc_id": roster_entry.pc_id,
        "parent_employee_id": roster_entry.parent_employee_id,
        "sender_phone": roster_entry.phone_number,
        "caption": None,
        "media_url": None,
        "image_hash": None,
        "overlay": None,
        "geofence_passed": None,
        "geofence_distance_m": None,
        "face_present": None,
        "face_count": None,
        "identity_verdict": None,
        "identity_score": None,
        "shift_status": "on_time",
        "attendance_date": norm_date,
        "attendance_status": "present",
        "verdict": "verified",
        "review_status": "n/a",
        "issues": [],
        "entry_type": "manual",
        "created_by": created_by,
        "reason": reason,
        "received_at_utc": f"{norm_date}T00:00:00Z",
    }
    result = await db.submissions.insert_one(doc)
    await delete_system_absences_today(employee_id, norm_date)
    doc["_id"] = str(result.inserted_id)
    return doc


async def save_attendance_override(
    employee_id: str,
    attendance_date: str,
    attendance_code: str,
    reason: str | None,
    changed_by: str,
) -> dict:
    person = await get_roster_by_employee_id(employee_id)
    if person is None:
        raise ValueError(f"No attendance participant found with ID: {employee_id}")
    if person.role == "PC":
        raise ValueError("Project coordinators are not attendance participants")

    norm_date = normalize_date_str(attendance_date)
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    existing = await db.attendance_overrides.find_one(
        {"employee_id": employee_id, "attendance_date": norm_date}
    )
    previous_code = existing.get("attendance_code") if existing else None
    if existing is None:
        submissions = await get_submissions_grouped(
            [employee_id], norm_date, norm_date
        )
        previous_submission = submissions.get(employee_id, {}).get(norm_date)
        if previous_submission is not None:
            previous_code = marker_for_submission(previous_submission)
    change = {
        "attendance_code": attendance_code,
        "reason": (reason or "").strip(),
        "changed_by": changed_by,
        "changed_at_utc": now,
    }
    await db.attendance_overrides.update_one(
        {"employee_id": employee_id, "attendance_date": norm_date},
        {
            "$set": change,
            "$setOnInsert": {
                "employee_id": employee_id,
                "attendance_date": norm_date,
                "person_role": person.role,
                "pc_id": person.pc_id,
                "parent_employee_id": person.parent_employee_id,
            },
            "$push": {
                "history": {
                    **change,
                    "previous_code": previous_code,
                }
            },
        },
        upsert=True,
    )
    return {
        "employee_id": employee_id,
        "attendance_date": norm_date,
        **change,
        "previous_code": previous_code,
    }


async def update_admin_last_seen(timestamp) -> None:
    db = get_db()
    await db.admin_state.update_one(
        {"_id": "admin"},
        {"$set": {"last_message_utc": timestamp}},
        upsert=True,
    )


async def register_webhook_event(event_id: str, payload: dict) -> bool:
    db = get_db()
    try:
        await db.webhook_events.insert_one({
            "event_id": event_id,
            "status": "received",
            "payload": payload,
        })
        return True
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            return False
        raise


async def claim_webhook_event(event_id: str) -> bool:
    db = get_db()
    doc = await db.webhook_events.find_one_and_update(
        {"event_id": event_id, "status": {"$in": ["received", "queued", "failed"]}},
        {"$set": {"status": "processing", "processing_started_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    return doc is not None


async def mark_webhook_queued(event_id: str) -> None:
    db = get_db()
    await db.webhook_events.update_one(
        {"event_id": event_id, "status": {"$in": ["received", "failed"]}},
        {"$set": {"status": "queued", "queued_at": datetime.now(timezone.utc)}}
    )


async def complete_webhook_event(event_id: str) -> None:
    db = get_db()
    await db.webhook_events.update_one(
        {"event_id": event_id},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
    )


async def fail_webhook_event(event_id: str, error: str, dead_letter: bool = False) -> None:
    db = get_db()
    await db.webhook_events.update_one(
        {"event_id": event_id},
        {"$set": {"status": "dead_letter" if dead_letter else "failed", "last_error": error[:2000], "last_failed_at": datetime.now(timezone.utc)}}
    )


async def create_notification(notification: dict) -> bool:
    db = get_db()
    try:
        await db.notifications.insert_one(notification)
        return True
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            return False
        raise


async def claim_notification(notification_id: str) -> bool:
    db = get_db()
    doc = await db.notifications.find_one_and_update(
        {"notification_id": notification_id, "status": {"$in": ["pending", "retry"]}},
        {"$set": {"status": "processing", "processing_started_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    return doc is not None


async def mark_notification_sent(notification_id: str) -> None:
    db = get_db()
    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc)}}
    )


async def mark_notification_skipped(notification_id: str) -> None:
    db = get_db()
    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "skipped", "skip_reason": "employee_reply_policy",
                  "skipped_at": datetime.now(timezone.utc)}}
    )


async def mark_notification_retry(notification_id: str, error: str) -> None:
    db = get_db()
    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "retry", "last_error": error[:2000], "last_failed_at": datetime.now(timezone.utc)}}
    )


class AdminUser(BaseModel):
    username: str
    password_hash: str
    is_active: bool = True
    role: Literal["super_admin", "manual_team", "viewer"] = "super_admin"
    pc_id: str | None = None


async def get_admin_user(username: str) -> AdminUser | None:
    db = get_db()
    doc = await db.admin_users.find_one({"username": username})
    if doc is None:
        return None
    return AdminUser(**doc)


async def list_admin_users() -> list[dict]:
    """Return account metadata without password hashes."""
    cursor = get_db().admin_users.find(
        {},
        {"_id": 0, "username": 1, "role": 1, "is_active": 1},
    ).sort("username", 1)
    users = []
    async for doc in cursor:
        doc.setdefault("role", "super_admin")
        doc.setdefault("is_active", True)
        users.append(doc)
    return users


async def create_admin_user(
    username: str,
    password_hash: str,
    role: Literal["super_admin", "manual_team", "viewer"] = "super_admin",
    pc_id: str | None = None,
) -> AdminUser:
    db = get_db()
    doc = {
        "username": username,
        "password_hash": password_hash,
        "is_active": True,
        "role": role,
        "pc_id": pc_id,
    }
    try:
        await db.admin_users.insert_one(doc)
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise ValueError(f"username {username} is already taken")
        raise
    return AdminUser(**doc)
