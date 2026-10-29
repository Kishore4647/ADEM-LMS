from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.api.routes.workflows import get_record, visible_students
from app.core.database import get_db
from app.models import CurriculumNode, StudentProfile, User
from app.models.workflows import PlatformSetting, QuestionSet, TestAssignment
from app.schemas.workflows import Payload
from app.services.access import audit, require_role

router = APIRouter(tags=["leaderboards and Hall of Fame"])


class CommunitySettings(Payload):
    ranking: Literal["average_percentage", "total_marks"]
    week_starts: Literal[0, 6]
    timezone: str = Field(min_length=1, max_length=80)
    hall_student_ids: list[int]
    public_display_authorised: bool


@router.get("/public/hall-of-fame")
def public_hall(db: Session = Depends(get_db)):
    setting = db.get(PlatformSetting, "community")
    if not setting or not setting.value.get("public_display_authorised"):
        return []
    result = []
    for id in setting.value["hall_student_ids"]:
        student = db.get(StudentProfile, id)
        if not student:
            continue
        account = db.get(User, student.user_id)
        if account.is_active:
            result.append(
                dict(
                    name=account.full_name or "Student",
                    class_name=db.get(CurriculumNode, student.class_node_id).name,
                )
            )
    return result


@router.get("/workspace/community/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user, "super_admin")
    setting = db.get(PlatformSetting, "community")
    return setting.value if setting else None


@router.put("/workspace/community/settings")
def save_settings(
    payload: CommunitySettings,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin")
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(400, "Choose a valid IANA timezone, such as Asia/Kolkata.")
    if payload.hall_student_ids and not payload.public_display_authorised:
        raise HTTPException(
            400,
            "Confirm public-display authorisation before selecting Hall of Fame students.",
        )
    for id in payload.hall_student_ids:
        get_record(db, StudentProfile, id)
    setting = db.get(PlatformSetting, "community")
    if not setting:
        setting = PlatformSetting(key="community", value=payload.model_dump())
        db.add(setting)
    else:
        setting.value = payload.model_dump()
    audit(db, user, "configure", "community", 0, payload.model_dump())
    db.commit()
    return {"ok": True}


@router.get("/workspace/leaderboard")
def leaderboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.get(PlatformSetting, "community")
    if not setting:
        return dict(configured=False, rows=[])
    config = setting.value
    zone = ZoneInfo(config["timezone"])
    now = datetime.now(zone)
    start = (now - timedelta(days=(now.weekday() - config["week_starts"]) % 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    students = visible_students(db, user)
    # Students may see class peers only in this explicitly permitted leaderboard.
    if user.role.value == "student" and students:
        me = students[0]
        students = list(
            db.scalars(
                select(StudentProfile).where(
                    StudentProfile.school_id == me.school_id,
                    StudentProfile.class_node_id == me.class_node_id,
                )
            )
        )
    rows = []
    for s in students:
        scores = []
        for assignment in db.scalars(
            select(TestAssignment).where(TestAssignment.student_id == s.id)
        ):
            q = db.get(QuestionSet, assignment.question_set_id)
            if q.category != "practice":
                continue
            eligible = [
                h
                for h in assignment.history
                if datetime.fromisoformat(h["submitted_at"]).astimezone(zone) >= start
            ]
            if not eligible:
                continue
            counted = (
                eligible[0]
                if q.policy["counted_attempt"] == "first"
                else max(eligible, key=lambda h: h["score"])
                if q.policy["counted_attempt"] == "best"
                else eligible[-1]
            )
            scores.append(
                (counted["score"], len(q.questions) * q.policy["correct_marks"])
            )
        if scores:
            value = (
                sum(score / maximum * 100 for score, maximum in scores) / len(scores)
                if config["ranking"] == "average_percentage"
                else sum(score for score, _ in scores)
            )
            account = db.get(User, s.user_id)
            if account.is_active:
                rows.append(
                    dict(
                        student_id=s.id,
                        name=account.full_name or "Student",
                        class_name=db.get(CurriculumNode, s.class_node_id).name,
                        score=round(value, 2),
                        tests=len(scores),
                    )
                )
    rows.sort(key=lambda r: (-r["score"], r["name"]))
    rank = 0
    previous = None
    for index, row in enumerate(rows, 1):
        if row["score"] != previous:
            rank = index
        row["rank"] = rank
        previous = row["score"]
    return dict(
        configured=True,
        week_start=start.date().isoformat(),
        metric=config["ranking"],
        rows=rows,
    )
