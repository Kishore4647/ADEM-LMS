import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import ROOT_DIR, get_settings
from app.core.database import get_db
from app.models import (
    AssessmentComponent,
    CurriculumBoard,
    CurriculumLevel,
    CurriculumNode,
    MarkRecord,
    School,
    StudentEnrollment,
    StudentProfile,
    User,
    UserRole,
    UserSchoolAssignment,
)
from app.models.workflows import (
    AuditEvent,
    ClassroomSession,
    LessonAsset,
    PrivateFile,
    ProgressPublication,
    QuestionSet,
    SessionMark,
    TeachingAssignment,
    TestAssignment,
)
from app.schemas.admin import SchoolCreate
from app.schemas.workflows import (
    Answers,
    AssetInput,
    BatchMarks,
    IssueInput,
    MarkInput,
    NotesInput,
    PublicationInput,
    QuestionSetInput,
    ReadinessInput,
    RetentionInput,
    ReviewInput,
    ScoreCorrection,
    SessionInput,
    StatusInput,
    StudentInput,
    StudentUpdate,
    TeachingInput,
    UserUpdate,
    YearCloseInput,
)
from app.services.access import (
    audit,
    check_school,
    check_student,
    check_teaching,
    path_for,
    record_dict,
    require_role,
    school_ids,
    subject_class,
)
from app.services.docx_import import import_docx
from app.services.files import validate_upload
from app.services.grading import quarterly

router = APIRouter(prefix="/workspace", tags=["LMS workflows"])
STORAGE = (
    Path(get_settings().uploads_dir)
    if get_settings().uploads_dir
    else ROOT_DIR / "backend" / "private_uploads"
)


def get_record(db, model, id):
    item = db.get(model, id)
    if item is None:
        raise HTTPException(404, "Record not found.")
    return item


@router.patch("/schools/{id}")
def school_status(
    id: int,
    payload: StatusInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    school = get_record(db, School, id)
    school.is_active = payload.is_active
    audit(db, user, "change_status", "school", id, payload.model_dump())
    db.commit()
    return {"ok": True}


@router.put("/schools/{id}")
def edit_school(
    id: int,
    payload: SchoolCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    school = get_record(db, School, id)
    before = record_dict(school)
    school.name = payload.name.strip()
    school.code = payload.code.strip().upper()
    school.address = payload.address
    audit(
        db,
        user,
        "update",
        "school",
        id,
        {"before": before, "after": record_dict(school)},
    )
    db.commit()
    return record_dict(school)


def mapped_subtopic(db, user, school_id, subtopic_id):
    check_school(db, user, school_id)
    path = path_for(db, subtopic_id)
    if len(path) != 5 or path[0].level != CurriculumLevel.SUB_TOPIC:
        raise HTTPException(400, "Select a valid curriculum sub-topic.")
    if user.role == UserRole.IST:
        check_teaching(db, user, school_id, path[3].id)
    if user.role == UserRole.STUDENT:
        student = db.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        if (
            not student
            or student.school_id != school_id
            or student.class_node_id != path[-1].id
        ):
            raise HTTPException(
                403, "This learning resource is not assigned to your class."
            )
    return path


def visible_students(db, user):
    query = select(StudentProfile)
    if user.role == UserRole.STUDENT:
        query = query.where(StudentProfile.user_id == user.id)
    elif user.role != UserRole.SUPER_ADMIN:
        query = query.where(StudentProfile.school_id.in_(school_ids(db, user)))
    students = list(db.scalars(query))
    if user.role == UserRole.IST:
        assignments = list(
            db.scalars(
                select(TeachingAssignment).where(TeachingAssignment.user_id == user.id)
            )
        )
        allowed = {(a.school_id, subject_class(db, a.subject_id)) for a in assignments}
        students = [s for s in students if (s.school_id, s.class_node_id) in allowed]
    return students


@router.get("/data")
def workspace_data(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    students = visible_students(db, user)
    ids = [s.id for s in students]
    allowed_schools = [
        id
        for id in school_ids(db, user)
        if db.get(School, id) and db.get(School, id).is_active
    ]
    global_access = user.role == UserRole.SUPER_ADMIN
    schools = list(
        db.scalars(
            select(School)
            if global_access
            else select(School).where(School.id.in_(allowed_schools))
        )
    )
    assets = list(
        db.scalars(
            select(LessonAsset)
            if global_access
            else select(LessonAsset).where(LessonAsset.school_id.in_(allowed_schools))
        )
    )
    sessions = list(
        db.scalars(
            select(ClassroomSession)
            if global_access
            else select(ClassroomSession).where(
                ClassroomSession.school_id.in_(allowed_schools)
            )
        )
    )
    marks = list(db.scalars(select(MarkRecord).where(MarkRecord.student_id.in_(ids))))
    if user.role == UserRole.STUDENT:
        sessions = []
    if user.role == UserRole.IST:
        sessions = [s for s in sessions if s.trainer_id == user.id]
        assigned = {
            (a.school_id, a.subject_id)
            for a in db.scalars(
                select(TeachingAssignment).where(TeachingAssignment.user_id == user.id)
            )
        }
        marks = [
            m
            for m in marks
            if (db.get(StudentProfile, m.student_id).school_id, m.subject_node_id)
            in assigned
        ]
    if user.role in {UserRole.STUDENT, UserRole.SCHOOL_MANAGEMENT}:
        assets = [a for a in assets if a.published]
    filtered_assets = []
    for asset in assets:
        try:
            mapped_subtopic(db, user, asset.school_id, asset.subtopic_id)
        except HTTPException:
            continue
        item = record_dict(asset)
        if user.role != UserRole.STUDENT:
            latest = {}
            for event in db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.entity == "asset",
                    AuditEvent.entity_id == asset.id,
                    AuditEvent.action == "confirm_readiness",
                )
                .order_by(AuditEvent.id)
            ):
                latest[event.actor_id] = event.detail.get("ready", False)
            item["ready_by"] = [actor for actor, ready in latest.items() if ready]
        filtered_assets.append(item)
    sets = list(
        db.scalars(
            select(QuestionSet)
            if global_access
            else select(QuestionSet).where(QuestionSet.school_id.in_(allowed_schools))
        )
    )
    assignments = list(
        db.scalars(select(TestAssignment).where(TestAssignment.student_id.in_(ids)))
    )
    if user.role == UserRole.STUDENT:
        sets = [s for s in sets if s.id in {a.question_set_id for a in assignments}]
    if user.role == UserRole.IST:
        allowed = {
            (a.school_id, a.subject_id)
            for a in db.scalars(
                select(TeachingAssignment).where(TeachingAssignment.user_id == user.id)
            )
        }
        sets = [
            s
            for s in sets
            if (s.school_id, path_for(db, s.subtopic_id)[3].id) in allowed
        ]
    assignments = [a for a in assignments if a.question_set_id in {s.id for s in sets}]
    set_data = []
    for s in sets:
        item = record_dict(s)
        item["question_count"] = len(s.questions)
        item.pop("questions")
        if user.role not in {UserRole.SUPER_ADMIN, UserRole.CONTENT_UPLOADER}:
            item.pop("source_file_id", None)
        set_data.append(item)
    attendance = []
    for link in db.scalars(select(SessionMark).where(SessionMark.student_id.in_(ids))):
        m = db.get(MarkRecord, link.mark_id)
        if m.id in {x.id for x in marks}:
            attendance.append(
                dict(
                    mark_id=m.id,
                    session_id=link.session_id,
                    student_id=link.student_id,
                    manual_present=link.manual_present,
                    final_status="Absent"
                    if m.is_absent or m.obtained_marks is None
                    else "Present",
                )
            )
    profiles = []
    for s in students:
        item = record_dict(s)
        account = db.get(User, s.user_id)
        item["name"] = account.full_name or account.email
        item["email"] = account.email
        item.pop("parent_phone", None)
        profiles.append(item)
    users = list(db.scalars(select(User))) if global_access else []
    enrollments = list(
        db.scalars(select(StudentEnrollment).where(StudentEnrollment.student_id.in_(ids)))
    )
    return dict(
        user=dict(
            id=user.id, name=user.full_name, email=user.email, role=user.role.value
        ),
        schools=[record_dict(s) for s in schools],
        users=[
            dict(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role.value,
                is_active=u.is_active,
                school_ids=school_ids(db, u),
            )
            for u in users
        ],
        boards=[record_dict(b) for b in db.scalars(select(CurriculumBoard))],
        nodes=[
            record_dict(n)
            for n in db.scalars(
                select(CurriculumNode).order_by(
                    CurriculumNode.sequence, CurriculumNode.id
                )
            )
        ],
        students=profiles,
        enrollments=[record_dict(e) for e in enrollments],
        teaching=[
            record_dict(a)
            for a in db.scalars(
                select(TeachingAssignment).where(
                    True if global_access else TeachingAssignment.user_id == user.id
                )
            )
        ],
        assets=filtered_assets,
        sessions=[record_dict(s) for s in sessions],
        marks=[record_dict(m) for m in marks],
        attendance=attendance,
        question_sets=set_data,
        assignments=[record_dict(a) for a in assignments],
        publications=[
            record_dict(p)
            for p in db.scalars(
                select(ProgressPublication).where(
                    ProgressPublication.student_id.in_(ids)
                )
            )
        ],
    )


@router.post("/students")
def save_student(
    payload: StudentInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "school_management")
    get_record(db, School, payload.school_id)
    check_school(db, user, payload.school_id)
    if payload.user_id is not None:
        if user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(403, "School Management must create a new student account.")
        account = get_record(db, User, payload.user_id)
        if account.role != UserRole.STUDENT:
            raise HTTPException(400, "Select a Student account.")
    else:
        email = str(payload.email).lower()
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "A user with this Google email already exists.")
        account = User(
            google_subject=f"pending:{uuid4().hex}",
            email=email,
            full_name=payload.full_name,
            role=UserRole.STUDENT,
        )
        db.add(account)
        db.flush()
    node = get_record(db, CurriculumNode, payload.class_node_id)
    if node.level != CurriculumLevel.CLASS:
        raise HTTPException(400, "Select a Class.")
    if db.scalar(select(StudentProfile).where(StudentProfile.user_id == account.id)):
        raise HTTPException(
            409,
            "Student already enrolled. Historical class transfers require a separate workflow.",
        )
    if db.scalar(
        select(StudentProfile).where(
            StudentProfile.school_id == payload.school_id,
            StudentProfile.admission_number == payload.admission_number,
        )
    ):
        raise HTTPException(409, "Admission number already exists in this school.")
    student = StudentProfile(
        user_id=account.id,
        school_id=payload.school_id,
        class_node_id=payload.class_node_id,
        admission_number=payload.admission_number,
        section=payload.section,
        academic_year=payload.academic_year,
    )
    db.add(student)
    db.flush()
    db.add(
        StudentEnrollment(
            student_id=student.id,
            academic_year=payload.academic_year,
            class_node_id=payload.class_node_id,
            section=payload.section,
        )
    )
    if not db.scalar(
        select(UserSchoolAssignment).where(
            UserSchoolAssignment.user_id == account.id,
            UserSchoolAssignment.school_id == payload.school_id,
        )
    ):
        db.add(UserSchoolAssignment(user_id=account.id, school_id=payload.school_id))
    audit(
        db,
        user,
        "enrol",
        "student",
        student.id,
        {
            "school_id": payload.school_id,
            "class_node_id": payload.class_node_id,
            "academic_year": payload.academic_year,
            "section": payload.section,
        },
    )
    db.commit()
    return {"id": student.id}


@router.put("/students/{id}")
def update_student(
    id: int,
    payload: StudentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "school_management")
    student = get_record(db, StudentProfile, id)
    check_school(db, user, student.school_id)
    account = get_record(db, User, student.user_id)
    email = str(payload.email).lower()
    conflict = db.scalar(select(User).where(User.email == email, User.id != account.id))
    if conflict:
        raise HTTPException(409, "A user with this Google email already exists.")
    admission_conflict = db.scalar(
        select(StudentProfile).where(
            StudentProfile.school_id == student.school_id,
            StudentProfile.admission_number == payload.admission_number,
            StudentProfile.id != student.id,
        )
    )
    if admission_conflict:
        raise HTTPException(409, "Admission number already exists in this school.")
    before = {
        "email": account.email,
        "full_name": account.full_name,
        "admission_number": student.admission_number,
        "section": student.section,
        "academic_year": student.academic_year,
    }
    if account.email != email:
        account.email = email
        account.google_subject = f"pending:{uuid4().hex}"
    account.full_name = payload.full_name
    student.admission_number = payload.admission_number
    student.section = payload.section
    previous_year = student.academic_year
    if previous_year and previous_year != payload.academic_year:
        raise HTTPException(400, "Academic year changes require the year-close workflow.")
    student.academic_year = payload.academic_year
    active = db.scalar(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.academic_year == student.academic_year,
        )
    )
    if active:
        active.section = payload.section
    elif not previous_year:
        db.add(
            StudentEnrollment(
                student_id=student.id,
                academic_year=payload.academic_year,
                class_node_id=student.class_node_id,
                section=payload.section,
            )
        )
    audit(db, user, "update", "student", id, {"before": before, "after": payload.model_dump(mode="json")})
    db.commit()
    return {"ok": True}


@router.patch("/students/{id}/retention")
def set_student_retention(
    id: int,
    payload: RetentionInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "school_management", "ist")
    student = get_record(db, StudentProfile, id)
    check_school(db, user, student.school_id)
    if student.status != "active":
        raise HTTPException(400, "Only active students can be retained.")
    if user.role == UserRole.IST:
        assigned_classes = {
            subject_class(db, assignment.subject_id)
            for assignment in db.scalars(
                select(TeachingAssignment).where(
                    TeachingAssignment.user_id == user.id,
                    TeachingAssignment.school_id == student.school_id,
                )
            )
        }
        if student.class_node_id not in assigned_classes:
            raise HTTPException(403, "The student is not in one of your assigned classes.")
    student.retain_next_year = payload.retain
    audit(db, user, "retention", "student", id, payload.model_dump())
    db.commit()
    return {"ok": True}


@router.post("/schools/{school_id}/close-academic-year")
def close_academic_year(
    school_id: int,
    payload: YearCloseInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "school_management")
    get_record(db, School, school_id)
    check_school(db, user, school_id)
    students = list(
        db.scalars(
            select(StudentProfile).where(
                StudentProfile.school_id == school_id,
                StudentProfile.academic_year == payload.current_academic_year,
                StudentProfile.status == "active",
            )
        )
    )
    if not students:
        raise HTTPException(400, "No active students found for that academic year.")
    promoted = retained = graduated = 0
    for student in students:
        current_class = get_record(db, CurriculumNode, student.class_node_id)
        history = db.scalar(
            select(StudentEnrollment).where(
                StudentEnrollment.student_id == student.id,
                StudentEnrollment.academic_year == payload.current_academic_year,
            )
        )
        if student.retain_next_year:
            next_class = current_class
            outcome = "retained"
            retained += 1
        else:
            ordered_classes = list(db.scalars(
                select(CurriculumNode)
                .where(
                    CurriculumNode.board_id == current_class.board_id,
                    CurriculumNode.level == CurriculumLevel.CLASS,
                )
                .order_by(CurriculumNode.sequence, CurriculumNode.id)
            ))
            current_index = next(
                index for index, item in enumerate(ordered_classes) if item.id == current_class.id
            )
            next_class = next(
                (
                    item
                    for item in ordered_classes[current_index + 1 :]
                    if item.is_active
                ),
                None,
            )
            if next_class is None:
                student.status = "graduated"
                if history:
                    history.outcome = "graduated"
                graduated += 1
                continue
            outcome = "promoted"
            promoted += 1
        if history:
            history.outcome = outcome
        student.class_node_id = next_class.id
        student.academic_year = payload.next_academic_year
        student.retain_next_year = False
        db.add(
            StudentEnrollment(
                student_id=student.id,
                academic_year=payload.next_academic_year,
                class_node_id=next_class.id,
                section=student.section or "Unassigned",
            )
        )
    summary = {"promoted": promoted, "retained": retained, "graduated": graduated}
    audit(db, user, "close_academic_year", "school", school_id, {**payload.model_dump(), **summary})
    db.commit()
    return summary


@router.post("/students/bulk")
async def bulk_students(
    school_id: int = Form(...),
    commit: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "school_management")
    get_record(db, School, school_id)
    check_school(db, user, school_id)
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "Student CSV must be 2 MB or smaller.")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Upload a UTF-8 CSV file.") from exc
    required = {"admission_number", "full_name", "email", "board", "class", "section", "academic_year"}
    if not rows or not required.issubset(rows[0]):
        raise HTTPException(400, "CSV columns: admission_number, full_name, email, board, class, section, academic_year")
    if len(rows) > 2000:
        raise HTTPException(400, "A bulk file can contain at most 2,000 students.")
    validated = []
    seen_emails: set[str] = set()
    seen_admissions: set[str] = set()
    errors = []
    for number, row in enumerate(rows, 2):
        email = row["email"].strip().lower()
        admission = row["admission_number"].strip()
        board = db.scalar(select(CurriculumBoard).where(CurriculumBoard.name == row["board"].strip()))
        class_node = db.scalar(
            select(CurriculumNode).where(
                CurriculumNode.board_id == (board.id if board else -1),
                CurriculumNode.level == CurriculumLevel.CLASS,
                CurriculumNode.name == row["class"].strip(),
            )
        )
        reason = None
        if not all(row.get(key, "").strip() for key in required):
            reason = "All columns are required."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            reason = "Invalid email."
        elif not re.fullmatch(r"(\d{4})-(\d{4})", row["academic_year"].strip()):
            reason = "Academic year must be YYYY-YYYY."
        elif int(row["academic_year"].strip()[5:]) != int(row["academic_year"].strip()[:4]) + 1:
            reason = "Academic year must contain consecutive years."
        elif not class_node:
            reason = "Board or class was not found."
        elif email in seen_emails or admission in seen_admissions:
            reason = "Duplicate email or admission number in file."
        elif db.scalar(select(User).where(User.email == email)):
            reason = "Email already exists."
        elif db.scalar(select(StudentProfile).where(StudentProfile.school_id == school_id, StudentProfile.admission_number == admission)):
            reason = "Admission number already exists in this school."
        if reason:
            errors.append({"row": number, "error": reason})
        else:
            seen_emails.add(email)
            seen_admissions.add(admission)
            validated.append({**row, "email": email, "admission_number": admission, "class_node_id": class_node.id})
    preview = {"total": len(rows), "valid": len(validated), "errors": errors}
    if not commit:
        return preview
    if errors:
        raise HTTPException(400, {"message": "Correct all rows before importing.", **preview})
    for row in validated:
        account = User(
            google_subject=f"pending:{uuid4().hex}",
            email=row["email"],
            full_name=row["full_name"].strip(),
            role=UserRole.STUDENT,
        )
        db.add(account)
        db.flush()
        student = StudentProfile(
            user_id=account.id,
            school_id=school_id,
            class_node_id=row["class_node_id"],
            admission_number=row["admission_number"],
            section=row["section"].strip(),
            academic_year=row["academic_year"].strip(),
        )
        db.add(student)
        db.flush()
        db.add_all([
            UserSchoolAssignment(user_id=account.id, school_id=school_id),
            StudentEnrollment(
                student_id=student.id,
                academic_year=student.academic_year,
                class_node_id=student.class_node_id,
                section=student.section,
            ),
        ])
    audit(db, user, "bulk_enrol", "school", school_id, {"count": len(validated)})
    db.commit()
    return {**preview, "imported": len(validated)}


@router.post("/teaching")
def save_teaching(
    payload: TeachingInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    account = get_record(db, User, payload.user_id)
    if account.role != UserRole.IST:
        raise HTTPException(400, "Select an IST account.")
    get_record(db, School, payload.school_id)
    subject_class(db, payload.subject_id)
    if db.scalar(select(TeachingAssignment).filter_by(**payload.model_dump())):
        raise HTTPException(409, "Already assigned.")
    assignment = TeachingAssignment(**payload.model_dump())
    db.add(assignment)
    db.flush()
    if not db.scalar(
        select(UserSchoolAssignment).where(
            UserSchoolAssignment.user_id == account.id,
            UserSchoolAssignment.school_id == payload.school_id,
        )
    ):
        db.add(UserSchoolAssignment(user_id=account.id, school_id=payload.school_id))
    audit(db, user, "assign", "teaching", assignment.id, payload.model_dump())
    db.commit()
    return {"id": assignment.id}


@router.patch("/users/{id}")
def update_user(
    id: int,
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    account = get_record(db, User, id)
    if account.id == user.id and not payload.is_active:
        raise HTTPException(400, "You cannot disable your own account.")
    for school in payload.school_ids:
        get_record(db, School, school)
    old = dict(is_active=account.is_active, school_ids=school_ids(db, account))
    # Removing school access while academic assignments exist would orphan records.
    required = {
        s.school_id
        for s in db.scalars(select(StudentProfile).where(StudentProfile.user_id == id))
    } | {
        a.school_id
        for a in db.scalars(
            select(TeachingAssignment).where(TeachingAssignment.user_id == id)
        )
    }
    if not required.issubset(set(payload.school_ids)):
        raise HTTPException(
            400, "Retain schools used by existing student/teaching assignments."
        )
    for a in list(
        db.scalars(
            select(UserSchoolAssignment).where(UserSchoolAssignment.user_id == id)
        )
    ):
        db.delete(a)
    for school in set(payload.school_ids):
        db.add(UserSchoolAssignment(user_id=id, school_id=school))
    account.is_active = payload.is_active
    audit(db, user, "update", "user", id, dict(before=old, after=payload.model_dump()))
    db.commit()
    return {"ok": True}


@router.post("/assets")
def create_asset(
    payload: AssetInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader", "ist")
    mapped_subtopic(db, user, payload.school_id, payload.subtopic_id)
    drive_id = None
    if payload.drive_url:
        match = re.fullmatch(
            r"https://drive\.google\.com/(?:file/d/([\w-]+)(?:/[^?]*)?(?:\?.*)?|(?:open|uc)\?id=([\w-]+)(?:&.*)?)",
            payload.drive_url,
        )
        if not match:
            raise HTTPException(400, "Use a valid Google Drive file link.")
        drive_id = match[1] or match[2]
    elif payload.file_id:
        file = get_record(db, PrivateFile, payload.file_id)
        if file.owner_id != user.id:
            raise HTTPException(403, "File access denied.")
    else:
        raise HTTPException(400, "Provide a Drive video link or uploaded resource.")
    asset = LessonAsset(
        school_id=payload.school_id,
        subtopic_id=payload.subtopic_id,
        title=payload.title,
        kind="video"
        if drive_id
        else "supplementary"
        if user.role == UserRole.IST
        else "document",
        drive_id=drive_id,
        file_id=payload.file_id,
        created_by=user.id,
        published=payload.published,
    )
    db.add(asset)
    db.flush()
    audit(db, user, "create", "asset", asset.id)
    db.commit()
    return record_dict(asset)


@router.post("/assets/{id}/issue")
def asset_issue(
    id: int,
    payload: IssueInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "ist", "content_uploader", "super_admin")
    asset = get_record(db, LessonAsset, id)
    mapped_subtopic(db, user, asset.school_id, asset.subtopic_id)
    asset.issue = payload.issue
    audit(db, user, "report_issue", "asset", id, payload.model_dump())
    db.commit()
    return {"ok": True}


@router.post("/assets/{id}/ready")
def confirm_readiness(
    id: int,
    payload: ReadinessInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "ist")
    asset = get_record(db, LessonAsset, id)
    mapped_subtopic(db, user, asset.school_id, asset.subtopic_id)
    audit(db, user, "confirm_readiness", "asset", id, payload.model_dump())
    db.commit()
    return {"ok": True}


@router.post("/assets/{id}/publish")
def asset_publish(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_role(user, "super_admin", "content_uploader")
    asset = get_record(db, LessonAsset, id)
    check_school(db, user, asset.school_id)
    asset.published = not asset.published
    audit(db, user, "publish" if asset.published else "unpublish", "asset", id)
    db.commit()
    return {"ok": True}


@router.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader", "ist")
    data = await file.read(20_000_001)
    if len(data) > 20_000_000:
        raise HTTPException(413, "Maximum upload size is 20 MB.")
    ext = Path(file.filename or "").suffix.lower()
    types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
    }
    if ext not in types:
        raise HTTPException(400, "Supported: DOCX, PDF, PNG, JPEG, MP3, XLSX, CSV.")
    try:
        validate_upload(data, ext)
    except ValueError as error:
        raise HTTPException(400, str(error))
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(400, "Invalid PDF.")
    if ext in {".docx", ".xlsx"} and not data.startswith(b"PK"):
        raise HTTPException(400, "Invalid Office file.")
    if ext == ".png" and not data.startswith(b"\x89PNG"):
        raise HTTPException(400, "Invalid PNG.")
    if ext in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8"):
        raise HTTPException(400, "Invalid JPEG.")
    STORAGE.mkdir(parents=True, exist_ok=True)
    key = uuid4().hex + ext
    (STORAGE / key).write_bytes(data)
    record = PrivateFile(
        name=Path(file.filename).name,
        media_type=types[ext],
        storage_key=key,
        owner_id=user.id,
    )
    db.add(record)
    db.flush()
    audit(db, user, "upload", "file", record.id, dict(name=record.name))
    db.commit()
    return {"id": record.id, "name": record.name}


@router.get("/files/{id}")
def download_file(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    file = get_record(db, PrivateFile, id)
    allowed = user.role == UserRole.SUPER_ADMIN or file.owner_id == user.id
    for asset in db.scalars(select(LessonAsset).where(LessonAsset.file_id == id)):
        try:
            mapped_subtopic(db, user, asset.school_id, asset.subtopic_id)
            if asset.published or user.role in {
                UserRole.CONTENT_UPLOADER,
                UserRole.IST,
            }:
                allowed = True
        except HTTPException:
            pass
    if user.role == UserRole.CONTENT_UPLOADER:
        for q in db.scalars(
            select(QuestionSet).where(QuestionSet.source_file_id == id)
        ):
            if q.school_id in school_ids(db, user):
                allowed = True
    if not allowed:
        raise HTTPException(403, "File access denied.")
    target = STORAGE / file.storage_key
    if not target.is_file():
        raise HTTPException(404, "File unavailable.")
    return FileResponse(
        target,
        media_type=file.media_type,
        filename=file.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/sessions")
def create_session(
    payload: SessionInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "ist")
    check_teaching(db, user, payload.school_id, payload.subject_id)
    for subtopic in payload.subtopic_ids:
        path = mapped_subtopic(db, user, payload.school_id, subtopic)
        if path[3].id != payload.subject_id:
            raise HTTPException(400, "Sub-topics must belong to this subject.")
    session = ClassroomSession(**payload.model_dump(), trainer_id=user.id)
    db.add(session)
    db.flush()
    audit(db, user, "create", "session", session.id)
    db.commit()
    return record_dict(session)


@router.post("/sessions/{id}/submit")
def submit_session(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session = get_record(db, ClassroomSession, id)
    require_role(user, "super_admin", "ist")
    check_teaching(db, user, session.school_id, session.subject_id)
    if user.role == UserRole.IST and session.trainer_id != user.id:
        raise HTTPException(403, "Only the reporting trainer may submit.")
    if session.status not in {"draft", "rejected"}:
        raise HTTPException(409, "Report already submitted.")
    students = list(
        db.scalars(
            select(StudentProfile).where(
                StudentProfile.school_id == session.school_id,
                StudentProfile.class_node_id == subject_class(db, session.subject_id),
            )
        )
    )
    for student in students:
        if not db.scalar(
            select(SessionMark).where(
                SessionMark.session_id == id, SessionMark.student_id == student.id
            )
        ):
            mark = MarkRecord(
                student_id=student.id,
                subject_node_id=session.subject_id,
                component=AssessmentComponent.ASSESSMENT,
                academic_period=session.period,
                title=f"Session #{id}",
                obtained_marks=None,
                maximum_marks=10,
                is_absent=True,
                entered_by_user_id=user.id,
                recorded_on=session.session_date,
            )
            db.add(mark)
            db.flush()
            db.add(
                SessionMark(
                    session_id=id,
                    student_id=student.id,
                    mark_id=mark.id,
                    manual_present=False,
                )
            )
    session.status = "resubmitted" if session.status == "rejected" else "submitted"
    audit(db, user, "submit", "session", id)
    db.commit()
    return {"ok": True}


@router.patch("/sessions/{id}")
def edit_session(
    id: int,
    payload: NotesInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "ist")
    session = get_record(db, ClassroomSession, id)
    check_teaching(db, user, session.school_id, session.subject_id)
    if user.role == UserRole.IST and session.trainer_id != user.id:
        raise HTTPException(403, "Only the reporting trainer may edit this report.")
    if session.status not in {"draft", "rejected"}:
        raise HTTPException(409, "Only draft or rejected reports can be edited.")
    before = record_dict(session)
    session.notes = payload.notes
    if payload.subtopic_ids is not None:
        for subtopic in payload.subtopic_ids:
            path = mapped_subtopic(db, user, session.school_id, subtopic)
            if path[3].id != session.subject_id:
                raise HTTPException(400, "Select sub-topics from the same subject.")
        session.subtopic_ids = payload.subtopic_ids
    if payload.session_date is not None:
        session.session_date = payload.session_date
        for link in db.scalars(select(SessionMark).where(SessionMark.session_id == id)):
            mark = db.get(MarkRecord, link.mark_id)
            previous = mark.recorded_on.isoformat()
            mark.recorded_on = payload.session_date
            audit(
                db,
                user,
                "correct_session_date",
                "mark",
                mark.id,
                {"before": previous, "after": payload.session_date.isoformat()},
            )
    audit(
        db,
        user,
        "correct_report",
        "session",
        id,
        dict(before=before, after=record_dict(session)),
    )
    db.commit()
    return {"ok": True}


@router.post("/sessions/{id}/review")
def review_session(
    id: int,
    payload: ReviewInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    session = get_record(db, ClassroomSession, id)
    if session.status not in {"submitted", "resubmitted"}:
        raise HTTPException(409, "Only submitted reports may be reviewed.")
    if payload.status == "rejected" and not payload.comment:
        raise HTTPException(400, "Rejection requires a comment.")
    session.status = payload.status
    session.review_comment = payload.comment
    audit(db, user, "review", "session", id, payload.model_dump())
    db.commit()
    return {"ok": True}


def write_mark(db, user, payload, id=None):
    student = get_record(db, StudentProfile, payload.student_id)
    check_teaching(db, user, student.school_id, payload.subject_node_id)
    if student.class_node_id != subject_class(db, payload.subject_node_id):
        raise HTTPException(400, "Subject does not belong to student class.")
    if payload.component == "quarterly_exam":
        duplicate = db.scalar(
            select(MarkRecord).where(
                MarkRecord.student_id == student.id,
                MarkRecord.subject_node_id == payload.subject_node_id,
                MarkRecord.academic_period == payload.academic_period,
                MarkRecord.component == AssessmentComponent.QUARTERLY_EXAM,
                MarkRecord.id != id if id else True,
            )
        )
        if duplicate:
            raise HTTPException(
                409, "Quarterly exam mark already exists; edit the existing mark."
            )
    data = payload.model_dump(exclude={"session_id", "manual_present"})
    data["component"] = AssessmentComponent(payload.component)
    mark = (
        get_record(db, MarkRecord, id)
        if id
        else MarkRecord(**data, entered_by_user_id=user.id)
    )
    before = record_dict(mark) if id else None
    affected_periods = {payload.academic_period}
    if id:
        affected_periods.add(mark.academic_period)
    if id:
        if (
            mark.student_id != payload.student_id
            or mark.subject_node_id != payload.subject_node_id
            or mark.component != data["component"]
        ):
            raise HTTPException(
                400, "Student, subject and component cannot change during correction."
            )
        for k, v in data.items():
            setattr(mark, k, v)
    else:
        db.add(mark)
    db.flush()
    if payload.session_id:
        session = get_record(db, ClassroomSession, payload.session_id)
        if (
            session.school_id != student.school_id
            or session.subject_id != payload.subject_node_id
            or session.period != payload.academic_period
        ):
            raise HTTPException(
                400, "Session does not match school, subject and period."
            )
        link = db.scalar(
            select(SessionMark).where(
                SessionMark.session_id == session.id,
                SessionMark.student_id == student.id,
            )
        )
        if link and link.mark_id != mark.id:
            raise HTTPException(409, "Session mark exists; edit the existing record.")
        if not link:
            link = SessionMark(
                session_id=session.id, student_id=student.id, mark_id=mark.id
            )
            db.add(link)
        link.manual_present = payload.manual_present
    elif id and db.scalar(select(SessionMark).where(SessionMark.mark_id == id)):
        link = db.scalar(select(SessionMark).where(SessionMark.mark_id == id))
        session = get_record(db, ClassroomSession, link.session_id)
        if payload.academic_period != session.period:
            raise HTTPException(
                400, "Retain the academic quarter of the linked session."
            )
    for publication in db.scalars(
        select(ProgressPublication).where(
            ProgressPublication.student_id == student.id,
            ProgressPublication.subject_id == payload.subject_node_id,
            ProgressPublication.period.in_(affected_periods),
        )
    ):
        publication.stale = True
    audit(
        db,
        user,
        "correct_mark" if id else "enter_mark",
        "mark",
        mark.id,
        dict(before=before, after=record_dict(mark)),
    )
    return mark


@router.post("/marks")
def create_mark(
    payload: MarkInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "ist")
    mark = write_mark(db, user, payload)
    db.commit()
    return record_dict(mark)


@router.post("/marks/batch")
def batch_marks(
    payload: BatchMarks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "ist")
    seen = set()
    saved = []
    for value in payload.marks:
        key = (
            value.student_id,
            value.subject_node_id,
            value.component,
            value.academic_period,
            value.session_id,
            value.title,
        )
        if key in seen:
            raise HTTPException(
                400, "The batch contains a duplicate student assessment."
            )
        seen.add(key)
        if value.session_id:
            link = db.scalar(
                select(SessionMark).where(
                    SessionMark.session_id == value.session_id,
                    SessionMark.student_id == value.student_id,
                )
            )
            existing = db.get(MarkRecord, link.mark_id) if link else None
        else:
            existing = db.scalar(
                select(MarkRecord).where(
                    MarkRecord.student_id == value.student_id,
                    MarkRecord.subject_node_id == value.subject_node_id,
                    MarkRecord.component == AssessmentComponent(value.component),
                    MarkRecord.academic_period == value.academic_period,
                    True
                    if value.component == "quarterly_exam"
                    else MarkRecord.title == value.title,
                )
            )
        saved.append(write_mark(db, user, value, existing.id if existing else None).id)
    db.commit()
    return {"saved": len(saved), "ids": saved}


@router.put("/marks/{id}")
def update_mark(
    id: int,
    payload: MarkInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "ist")
    mark = write_mark(db, user, payload, id)
    db.commit()
    return record_dict(mark)


@router.post("/question-sets/import")
async def import_questions(
    file_id: int = Form(...),
    school_id: int = Form(...),
    subtopic_id: int = Form(...),
    difficulty: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader")
    mapped_subtopic(db, user, school_id, subtopic_id)
    if difficulty not in {"easy", "medium", "hard"}:
        raise HTTPException(400, "Select difficulty.")
    file = get_record(db, PrivateFile, file_id)
    if file.owner_id != user.id and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(403, "Source file access denied.")
    if not file.name.lower().endswith(".docx"):
        raise HTTPException(400, "Upload DOCX for MCQ import.")
    try:
        parsed = import_docx((STORAGE / file.storage_key).read_bytes())
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(
            422, "The Word file is corrupt or contains an unsupported XML structure."
        )
    item = QuestionSet(
        school_id=school_id,
        subtopic_id=subtopic_id,
        title=parsed["metadata"]["Lesson"],
        difficulty=difficulty,
        questions=parsed["questions"],
        source_file_id=file.id,
        created_by=user.id,
        policy={},
    )
    db.add(item)
    db.flush()
    audit(db, user, "import", "question_set", item.id)
    db.commit()
    return {"id": item.id, "questions": item.questions, "metadata": parsed["metadata"]}


@router.get("/question-sets/{id}")
def question_detail(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_role(user, "super_admin", "content_uploader")
    item = get_record(db, QuestionSet, id)
    check_school(db, user, item.school_id)
    return record_dict(item)


@router.put("/question-sets/{id}")
def edit_questions(
    id: int,
    payload: QuestionSetInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader")
    item = get_record(db, QuestionSet, id)
    check_school(db, user, item.school_id)
    if item.status != "draft":
        raise HTTPException(
            409, "Dispatched questions are locked to preserve scoring history."
        )
    item.title = payload.title
    item.questions = [q.model_dump() for q in payload.questions]
    item.policy = payload.policy.model_dump()
    item.category = payload.category
    audit(db, user, "edit", "question_set", id)
    db.commit()
    return {"ok": True}


@router.post("/question-sets/{id}/dispatch")
def dispatch_questions(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_role(user, "super_admin", "content_uploader")
    item = db.scalar(select(QuestionSet).where(QuestionSet.id == id).with_for_update())
    if not item:
        raise HTTPException(404, "Question set not found.")
    check_school(db, user, item.school_id)
    if not item.policy:
        raise HTTPException(
            400, "Review questions and configure scoring and attempts before dispatch."
        )
    class_id = path_for(db, item.subtopic_id)[-1].id
    students = list(
        db.scalars(
            select(StudentProfile).where(
                StudentProfile.school_id == item.school_id,
                StudentProfile.class_node_id == class_id,
            )
        )
    )
    if not students:
        raise HTTPException(400, "Enrol eligible students before dispatch.")
    for s in students:
        if not db.scalar(
            select(TestAssignment).where(
                TestAssignment.question_set_id == id, TestAssignment.student_id == s.id
            )
        ):
            db.add(TestAssignment(question_set_id=id, student_id=s.id, history=[]))
    item.status = "dispatched"
    audit(db, user, "dispatch", "question_set", id, dict(students=len(students)))
    db.commit()
    return {"assigned": len(students)}


def owned_attempt(db, user, id):
    require_role(user, "student")
    assignment = get_record(db, TestAssignment, id)
    student = get_record(db, StudentProfile, assignment.student_id)
    check_student(db, user, student)
    return assignment, get_record(db, QuestionSet, assignment.question_set_id)


@router.get("/attempts/{id}")
def get_attempt(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    assignment, item = owned_attempt(db, user, id)
    remaining = len(assignment.history) < item.policy["max_attempts"]
    questions = [
        dict(prompt=q["prompt"], options=q["options"], hint=q["hint"])
        for q in item.questions
    ]
    # Explanations/keys are revealed only once all allowed attempts are exhausted.
    if not remaining and assignment.submitted_at:
        questions = item.questions
    return dict(
        id=id,
        title=item.title,
        questions=questions,
        policy=item.policy,
        attempts=len(assignment.history),
        remaining=remaining,
        score=assignment.score,
        history=assignment.history,
        explanations=[q["explanation"] for q in item.questions]
        if assignment.submitted_at
        else [],
    )


@router.post("/attempts/{id}/submit")
def submit_attempt(
    id: int,
    payload: Answers,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "student")
    assignment = db.scalar(
        select(TestAssignment).where(TestAssignment.id == id).with_for_update()
    )
    if not assignment:
        raise HTTPException(404, "Assessment assignment not found.")
    check_student(db, user, get_record(db, StudentProfile, assignment.student_id))
    item = get_record(db, QuestionSet, assignment.question_set_id)
    if len(assignment.history) >= item.policy["max_attempts"]:
        raise HTTPException(409, "Maximum attempts reached.")
    if len(payload.answers) != len(item.questions) or any(
        x is not None and (isinstance(x, bool) or x not in range(4))
        for x in payload.answers
    ):
        raise HTTPException(400, "Invalid answers.")
    score = Decimal(0)
    for answer, q in zip(payload.answers, item.questions):
        if answer == q["correct"]:
            score += Decimal(str(item.policy["correct_marks"]))
        elif answer is not None:
            score -= Decimal(str(item.policy["incorrect_penalty"]))
    history = assignment.history + [
        dict(
            answers=payload.answers,
            score=float(score),
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )
    ]
    selected = (
        history[0]
        if item.policy["counted_attempt"] == "first"
        else max(history, key=lambda x: x["score"])
        if item.policy["counted_attempt"] == "best"
        else history[-1]
    )
    assignment.history = history
    assignment.answers = selected["answers"]
    assignment.score = selected["score"]
    assignment.submitted_at = datetime.now(timezone.utc)
    audit(
        db,
        user,
        "submit",
        "attempt",
        id,
        dict(score=float(score), attempt=len(history)),
    )
    db.commit()
    return dict(
        score=float(score),
        counted_score=assignment.score,
        explanations=[q["explanation"] for q in item.questions],
    )


@router.post("/attempts/{id}/correct")
def correct_mcq_score(
    id: int,
    payload: ScoreCorrection,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    assignment = db.scalar(
        select(TestAssignment).where(TestAssignment.id == id).with_for_update()
    )
    if not assignment:
        raise HTTPException(404, "Assessment assignment not found.")
    item = get_record(db, QuestionSet, assignment.question_set_id)
    if payload.attempt_number > len(assignment.history):
        raise HTTPException(400, "Select a submitted attempt.")
    count = len(item.questions)
    if (
        not -count * item.policy["incorrect_penalty"]
        <= payload.score
        <= count * item.policy["correct_marks"]
    ):
        raise HTTPException(
            400, "Corrected score is outside the configured assessment range."
        )
    history = [dict(h) for h in assignment.history]
    target = history[payload.attempt_number - 1]
    previous = target["score"]
    target.setdefault("original_score", previous)
    target["score"] = payload.score
    selected = (
        history[0]
        if item.policy["counted_attempt"] == "first"
        else max(history, key=lambda h: h["score"])
        if item.policy["counted_attempt"] == "best"
        else history[-1]
    )
    assignment.history = history
    assignment.score = selected["score"]
    assignment.answers = selected["answers"]
    audit(
        db,
        user,
        "correct_mcq_score",
        "attempt",
        id,
        dict(
            attempt_number=payload.attempt_number,
            original_score=previous,
            corrected_score=payload.score,
            counted_score=assignment.score,
            reason=payload.reason,
        ),
    )
    db.commit()
    return {"counted_score": assignment.score}


def result_for(db, user, student_id, subject_id, period):
    student = get_record(db, StudentProfile, student_id)
    check_student(db, user, student)
    if user.role == UserRole.IST:
        check_teaching(db, user, student.school_id, subject_id)
    if subject_class(db, subject_id) != student.class_node_id:
        raise HTTPException(400, "Subject/class mismatch.")
    records = list(
        db.scalars(
            select(MarkRecord).where(
                MarkRecord.student_id == student_id,
                MarkRecord.subject_node_id == subject_id,
                MarkRecord.academic_period == period,
            )
        )
    )
    return quarterly(records, "exclude")


@router.get("/results")
def result(
    student_id: int,
    subject_id: int,
    period: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return result_for(db, user, student_id, subject_id, period)


@router.post("/progress/publish")
def publish_progress(
    payload: PublicationInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    result = result_for(
        db, user, payload.student_id, payload.subject_id, payload.period
    )
    if not result["complete"]:
        raise HTTPException(
            400, "Enter all three components before publishing a progress card."
        )
    record = db.scalar(
        select(ProgressPublication).where(
            ProgressPublication.student_id == payload.student_id,
            ProgressPublication.subject_id == payload.subject_id,
            ProgressPublication.period == payload.period,
        )
    )
    if not record:
        record = ProgressPublication(
            **payload.model_dump(), snapshot=result, published_by=user.id
        )
        db.add(record)
    else:
        record.snapshot = result
        record.stale = False
        record.published_by = user.id
    db.flush()
    audit(db, user, "publish", "progress_card", record.id, result)
    db.commit()
    return record_dict(record)


@router.get("/progress/{id}/pdf")
def progress_pdf(
    id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    card = get_record(db, ProgressPublication, id)
    student = get_record(db, StudentProfile, card.student_id)
    check_student(db, user, student)
    if user.role == UserRole.IST:
        check_teaching(db, user, student.school_id, card.subject_id)
    if card.stale:
        raise HTTPException(
            409, "Marks changed. Super Admin must republish the progress card."
        )
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle("ADEM LMS Quarterly Progress Card")
    y = 790
    account = db.get(User, student.user_id)
    lines = [
        ("ADEM LMS", 22),
        ("Quarterly Progress Card", 16),
        (account.full_name or account.email, 13),
        (f"School: {db.get(School, student.school_id).name}", 11),
        (
            f"Subject: {db.get(CurriculumNode, card.subject_id).name} | Period: {card.period}",
            11,
        ),
        ("Activity sheet / 10: " + str(card.snapshot["activity"]), 12),
        ("Classroom assessment / 10: " + str(card.snapshot["assessment"]), 12),
        ("Quarterly examination / 80: " + str(card.snapshot["exam"]), 12),
        ("Total / 100: " + str(card.snapshot["total"]), 16),
    ]
    for line, size in lines:
        pdf.setFont("Helvetica", size)
        for part in [line[i : i + 75] for i in range(0, len(line), 75)]:
            pdf.drawString(50, y, part)
            y -= 24
        y -= 10
    pdf.save()
    return Response(
        output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="progress-{id}.pdf"'},
    )


@router.get("/audit")
def audit_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user, "super_admin")
    return [
        record_dict(a)
        for a in db.scalars(
            select(AuditEvent).order_by(AuditEvent.id.desc()).limit(500)
        )
    ]


@router.get("/exports/marks.csv")
def export_marks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import csv

    records = workspace_data(user, db)
    names = {s["id"]: s["name"] for s in records["students"]}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "student",
            "subject_id",
            "component",
            "academic_period",
            "title",
            "marks",
            "maximum",
            "absent",
        ]
    )

    def safe(value):
        value = str(value) if value is not None else ""
        return (
            "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
        )

    for record in records["marks"]:
        writer.writerow(
            [
                safe(names[record["student_id"]]),
                record["subject_node_id"],
                record["component"],
                safe(record["academic_period"]),
                safe(record["title"]),
                record["obtained_marks"],
                record["maximum_marks"],
                record["is_absent"],
            ]
        )
    audit(db, user, "export", "marks", 0, dict(rows=len(records["marks"])))
    db.commit()
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="adem-marks.csv"'},
    )
