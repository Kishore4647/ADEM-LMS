from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=64)
    address: str | None = None


class SchoolResponse(SchoolCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


class UserProvision(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole
    school_ids: list[int] = []


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool


class DashboardSummary(BaseModel):
    schools: int
    users: int
    students: int
    curriculum_nodes: int
