from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImportJob(Base):
    __tablename__ = "marks_import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("private_files.id"))
    status: Mapped[str] = mapped_column(String(30), default="validated")
    rows: Mapped[list] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
