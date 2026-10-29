from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (UniqueConstraint("user_id", "school_id", "subject_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("curriculum_nodes.id"))


class LessonAsset(Base):
    __tablename__ = "lesson_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    subtopic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_nodes.id"))
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30))
    drive_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("private_files.id"), nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrivateFile(Base):
    __tablename__ = "private_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ClassroomSession(Base):
    __tablename__ = "classroom_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("curriculum_nodes.id"))
    trainer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    session_date: Mapped[date] = mapped_column(Date)
    period: Mapped[str] = mapped_column(String(80))
    subtopic_ids: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    review_comment: Mapped[str] = mapped_column(Text, default="")


class SessionMark(Base):
    __tablename__ = "session_marks"
    __table_args__ = (UniqueConstraint("session_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("classroom_sessions.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"))
    mark_id: Mapped[int] = mapped_column(ForeignKey("mark_records.id"))
    manual_present: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestionSet(Base):
    __tablename__ = "question_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    subtopic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_nodes.id"))
    title: Mapped[str] = mapped_column(String(255))
    difficulty: Mapped[str] = mapped_column(String(20))
    questions: Mapped[list] = mapped_column(JSON)
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("private_files.id"), nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = mapped_column(String(30), default="assessment")


class TestAssignment(Base):
    __tablename__ = "test_assignments"
    __table_args__ = (UniqueConstraint("question_set_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"))
    answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    history: Mapped[list] = mapped_column(JSON, default=list)


class ProgressPublication(Base):
    __tablename__ = "progress_publications"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("curriculum_nodes.id"))
    period: Mapped[str] = mapped_column(String(80))
    snapshot: Mapped[dict] = mapped_column(JSON)
    published_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
