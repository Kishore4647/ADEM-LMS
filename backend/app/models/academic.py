import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CurriculumLevel(str, enum.Enum):
    CLASS = "class"
    SUBJECT = "subject"
    CHAPTER = "chapter"
    TOPIC = "topic"
    SUB_TOPIC = "sub_topic"


class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSchoolAssignment(Base):
    __tablename__ = "user_school_assignments"
    __table_args__ = (UniqueConstraint("user_id", "school_id", name="uq_user_school"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CurriculumBoard(Base):
    __tablename__ = "curriculum_boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CurriculumNode(Base):
    """One ordered curriculum tree: Class -> Subject -> Chapter -> Topic -> Sub-topic."""

    __tablename__ = "curriculum_nodes"
    __table_args__ = (
        UniqueConstraint("board_id", "parent_id", "name", name="uq_curriculum_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_boards.id"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_nodes.id"), nullable=True, index=True
    )
    level: Mapped[CurriculumLevel] = mapped_column(
        Enum(CurriculumLevel, name="curriculum_level"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    class_node_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_nodes.id"), index=True
    )
    admission_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parent_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)


class AssessmentComponent(str, enum.Enum):
    ASSESSMENT = "assessment"
    ACTIVITY = "activity"
    QUARTERLY_EXAM = "quarterly_exam"


class MarkRecord(Base):
    """Stores all IST-entered marks; assessment/activity conversion happens at reporting time."""

    __tablename__ = "mark_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id"), index=True
    )
    subject_node_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_nodes.id"), index=True
    )
    component: Mapped[AssessmentComponent] = mapped_column(
        Enum(AssessmentComponent, name="assessment_component")
    )
    academic_period: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255))
    obtained_marks: Mapped[float | None] = mapped_column(nullable=True)
    maximum_marks: Mapped[float] = mapped_column(nullable=False)
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    entered_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recorded_on: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
