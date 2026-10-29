from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserRole


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    role: UserRole
    is_active: bool
