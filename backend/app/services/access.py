from fastapi import HTTPException
from sqlalchemy import select

from app.models import (
    CurriculumLevel,
    CurriculumNode,
    School,
    UserRole,
    UserSchoolAssignment,
)
from app.models.workflows import AuditEvent, TeachingAssignment


def require_role(user, *roles):
    if user.role.value not in roles:
        raise HTTPException(403, "This action is not allowed for your role.")


def school_ids(db, user):
    return list(
        db.scalars(
            select(UserSchoolAssignment.school_id)
            .join(School, School.id == UserSchoolAssignment.school_id)
            .where(UserSchoolAssignment.user_id == user.id, School.is_active.is_(True))
        )
    )


def check_school(db, user, school_id):
    if user.role == UserRole.SUPER_ADMIN:
        return
    school = db.get(School, school_id)
    if not school or not school.is_active:
        raise HTTPException(403, "School is inactive or unavailable.")
    if school_id not in school_ids(db, user):
        raise HTTPException(403, "School access denied.")


def subject_class(db, subject_id):
    subject = db.get(CurriculumNode, subject_id)
    if not subject or subject.level != CurriculumLevel.SUBJECT:
        raise HTTPException(400, "Select a valid subject.")
    return subject.parent_id


def path_for(db, node_id):
    result = []
    node = db.get(CurriculumNode, node_id)
    while node:
        result.append(node)
        node = db.get(CurriculumNode, node.parent_id) if node.parent_id else None
    return result


def check_teaching(db, user, school_id, subject_id):
    check_school(db, user, school_id)
    subject_class(db, subject_id)
    if user.role == UserRole.IST and not db.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.user_id == user.id,
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.subject_id == subject_id,
        )
    ):
        raise HTTPException(403, "This subject is not assigned to you.")


def check_student(db, user, student):
    if not student:
        raise HTTPException(404, "Student not found.")
    if user.role == UserRole.STUDENT:
        if student.user_id != user.id:
            raise HTTPException(403, "Student access denied.")
    else:
        check_school(db, user, student.school_id)


def audit(db, user, action, entity, entity_id, detail=None):
    db.add(
        AuditEvent(
            actor_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail or {},
        )
    )


def record_dict(record):
    from datetime import date, datetime
    from enum import Enum

    result = {}
    for col in record.__table__.columns:
        value = getattr(record, col.name)
        result[col.name] = (
            value.value
            if isinstance(value, Enum)
            else value.isoformat()
            if isinstance(value, (date, datetime))
            else value
        )
    return result
