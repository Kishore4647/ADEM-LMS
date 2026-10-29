from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.database import get_db
from app.models import (
    CurriculumNode,
    School,
    StudentProfile,
    User,
    UserRole,
    UserSchoolAssignment,
)
from app.schemas.admin import (
    AdminUserResponse,
    DashboardSummary,
    SchoolCreate,
    SchoolResponse,
    UserProvision,
)
from app.services.access import audit

router = APIRouter(prefix="/admin", tags=["super admin"])


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin access required"
        )
    return user


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    _: User = Depends(require_super_admin), db: Session = Depends(get_db)
) -> DashboardSummary:
    return DashboardSummary(
        schools=db.scalar(select(func.count()).select_from(School)) or 0,
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        students=db.scalar(select(func.count()).select_from(StudentProfile)) or 0,
        curriculum_nodes=db.scalar(select(func.count()).select_from(CurriculumNode))
        or 0,
    )


@router.get("/schools", response_model=list[SchoolResponse])
def list_schools(
    _: User = Depends(require_super_admin), db: Session = Depends(get_db)
) -> list[School]:
    return list(db.scalars(select(School).order_by(School.name)))


@router.post(
    "/schools", response_model=SchoolResponse, status_code=status.HTTP_201_CREATED
)
def create_school(
    payload: SchoolCreate,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> School:
    code = payload.code.strip().upper()
    if db.scalar(
        select(School).where(
            (School.name == payload.name.strip()) | (School.code == code)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="School name or code already exists",
        )
    school = School(name=payload.name.strip(), code=code, address=payload.address)
    db.add(school)
    db.flush()
    audit(db, _, "create", "school", school.id)
    db.commit()
    db.refresh(school)
    return school


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    _: User = Depends(require_super_admin), db: Session = Depends(get_db)
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post(
    "/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED
)
def provision_user(
    payload: UserProvision,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> User:
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    schools = (
        list(db.scalars(select(School).where(School.id.in_(payload.school_ids))))
        if payload.school_ids
        else []
    )
    if len(schools) != len(set(payload.school_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more schools do not exist",
        )
    user = User(
        google_subject=f"pending:{uuid4().hex}",
        email=email,
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.flush()
    db.add_all(
        [
            UserSchoolAssignment(user_id=user.id, school_id=school.id)
            for school in schools
        ]
    )
    audit(
        db,
        _,
        "provision",
        "user",
        user.id,
        dict(email=email, role=payload.role.value, school_ids=payload.school_ids),
    )
    db.commit()
    db.refresh(user)
    return user
