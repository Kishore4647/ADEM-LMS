from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentInput(Payload):
    user_id: int | None = None
    school_id: int
    class_node_id: int
    admission_number: str = Field(min_length=1, max_length=80)
    section: str = Field(min_length=1, max_length=40)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def account_or_identity(self):
        if self.user_id is None and (not self.full_name or not self.email):
            raise ValueError("Enter the student's name and Google email.")
        start, end = map(int, self.academic_year.split("-"))
        if end != start + 1:
            raise ValueError("Academic year must contain consecutive years.")
        return self


class StudentUpdate(Payload):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    admission_number: str = Field(min_length=1, max_length=80)
    section: str = Field(min_length=1, max_length=40)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")

    @model_validator(mode="after")
    def valid_academic_year(self):
        start, end = map(int, self.academic_year.split("-"))
        if end != start + 1:
            raise ValueError("Academic year must contain consecutive years.")
        return self


class RetentionInput(Payload):
    retain: bool


class YearCloseInput(Payload):
    current_academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    next_academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")

    @model_validator(mode="after")
    def consecutive_years(self):
        current_start, current_end = map(int, self.current_academic_year.split("-"))
        next_start, next_end = map(int, self.next_academic_year.split("-"))
        if current_end != current_start + 1 or next_end != next_start + 1:
            raise ValueError("Academic years must contain consecutive years.")
        if next_start != current_end:
            raise ValueError("The next academic year must follow the current year.")
        return self


class TeachingInput(Payload):
    user_id: int
    school_id: int
    subject_id: int


class UserUpdate(Payload):
    school_ids: list[int]
    is_active: bool


class AssetInput(Payload):
    school_id: int
    subtopic_id: int
    title: str = Field(min_length=1, max_length=255)
    drive_url: str | None = None
    file_id: int | None = None
    published: bool = False


class SessionInput(Payload):
    school_id: int
    subject_id: int
    session_date: date
    period: str = Field(min_length=1, max_length=40)
    subtopic_ids: list[int] = Field(min_length=1)
    notes: str = Field(default="", max_length=10000)


class ReviewInput(Payload):
    status: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=4000)


class MarkInput(Payload):
    student_id: int
    subject_node_id: int
    component: Literal["assessment", "activity", "quarterly_exam"]
    academic_period: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=255)
    obtained_marks: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    maximum_marks: float = Field(gt=0, allow_inf_nan=False)
    is_absent: bool = False
    session_id: int | None = None
    manual_present: bool = False

    @model_validator(mode="after")
    def validate_marks(self):
        if self.is_absent:
            if self.obtained_marks is not None:
                raise ValueError("Absent marks must be blank.")
        elif self.obtained_marks is None:
            raise ValueError("Enter a mark, including zero, or mark Absent.")
        if self.obtained_marks is not None and self.obtained_marks > self.maximum_marks:
            raise ValueError("Mark exceeds maximum.")
        if self.component == "quarterly_exam" and self.maximum_marks != 80:
            raise ValueError("Quarterly examination maximum must be 80.")
        if self.session_id is not None and self.component != "assessment":
            raise ValueError(
                "Only classroom assessments can determine session attendance."
            )
        return self


class Question(Payload):
    prompt: str = Field(min_length=1, max_length=5_000_000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=5_000_000)
    hint: str = Field(min_length=1, max_length=5_000_000)


class Policy(Payload):
    correct_marks: float = Field(gt=0, le=100, allow_inf_nan=False)
    incorrect_penalty: float = Field(ge=0, le=100, allow_inf_nan=False)
    max_attempts: int = Field(ge=1, le=20)
    counted_attempt: Literal["first", "latest", "best"]


class QuestionSetInput(Payload):
    title: str = Field(min_length=1, max_length=255)
    questions: list[Question] = Field(min_length=1, max_length=200)
    policy: Policy
    category: Literal["assessment", "practice"] = "assessment"


class Answers(Payload):
    answers: list[int | None]


class PublicationInput(Payload):
    student_id: int
    subject_id: int
    period: str = Field(min_length=1, max_length=40)


class IssueInput(Payload):
    issue: str = Field(min_length=1, max_length=2000)


class NotesInput(Payload):
    notes: str = Field(max_length=10000)
    subtopic_ids: list[int] | None = Field(default=None, min_length=1)
    session_date: date | None = None


class StatusInput(Payload):
    is_active: bool


class ReadinessInput(Payload):
    ready: bool


class BatchMarks(Payload):
    marks: list[MarkInput] = Field(min_length=1, max_length=200)


class ScoreCorrection(Payload):
    attempt_number: int = Field(ge=1)
    score: float = Field(allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)
