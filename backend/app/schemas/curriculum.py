from pydantic import BaseModel, ConfigDict, Field

from app.models.academic import CurriculumLevel


class BoardCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class BoardResponse(BoardCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class CurriculumNodeCreate(BaseModel):
    board_id: int
    parent_id: int | None = None
    level: CurriculumLevel
    name: str = Field(min_length=1, max_length=255)
    sequence: int = Field(default=1, ge=1)


class CurriculumNodeResponse(CurriculumNodeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class CurriculumNodeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=255)
    sequence: int = Field(ge=1)
