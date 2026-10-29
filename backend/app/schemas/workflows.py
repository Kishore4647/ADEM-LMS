from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentInput(Payload):
    user_id: int
    school_id: int
    class_node_id: int
    admission_number: str | None = None


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
