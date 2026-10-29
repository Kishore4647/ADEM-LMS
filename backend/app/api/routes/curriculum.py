from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.database import get_db
from app.models import CurriculumBoard, CurriculumLevel, CurriculumNode, User
from app.schemas.curriculum import (
    BoardCreate,
    BoardResponse,
    CurriculumNodeCreate,
    CurriculumNodeEdit,
    CurriculumNodeResponse,
)
from app.services.access import audit, record_dict, require_role

router = APIRouter(prefix="/curriculum", tags=["curriculum"])
PARENTS: dict[CurriculumLevel, CurriculumLevel | None] = {
    CurriculumLevel.CLASS: None,
    CurriculumLevel.SUBJECT: CurriculumLevel.CLASS,
    CurriculumLevel.CHAPTER: CurriculumLevel.SUBJECT,
    CurriculumLevel.TOPIC: CurriculumLevel.CHAPTER,
    CurriculumLevel.SUB_TOPIC: CurriculumLevel.TOPIC,
}


@router.patch("/nodes/{id}", response_model=CurriculumNodeResponse)
def edit_node(
    id: int,
    payload: CurriculumNodeEdit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader")
    node = db.get(CurriculumNode, id)
    if not node:
        raise HTTPException(404, "Curriculum record not found.")
    if db.scalar(
        select(CurriculumNode).where(
            CurriculumNode.id != id,
            CurriculumNode.board_id == node.board_id,
            CurriculumNode.parent_id == node.parent_id,
            CurriculumNode.name == payload.name,
        )
    ):
        raise HTTPException(409, "This name already exists under the selected parent.")
    before = record_dict(node)
    node.name = payload.name
    node.sequence = payload.sequence
    audit(
        db,
        user,
        "update",
        "curriculum",
        id,
        {"before": before, "after": record_dict(node)},
    )
    db.commit()
    return node


@router.patch("/boards/{id}", response_model=BoardResponse)
def edit_board(
    id: int,
    payload: BoardCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, "super_admin", "content_uploader")
    board = db.get(CurriculumBoard, id)
    if not board:
        raise HTTPException(404, "Board not found.")
    before = board.name
    board.name = payload.name.strip()
    audit(db, user, "rename", "board", id, {"before": before, "after": board.name})
    db.commit()
    return board


@router.get("/boards", response_model=list[BoardResponse])
def list_boards(
    _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CurriculumBoard]:
    return list(db.scalars(select(CurriculumBoard).order_by(CurriculumBoard.name)))


@router.post(
    "/boards", response_model=BoardResponse, status_code=status.HTTP_201_CREATED
)
def create_board(
    payload: BoardCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurriculumBoard:
    require_role(_, "super_admin", "content_uploader")
    if db.scalar(
        select(CurriculumBoard).where(CurriculumBoard.name == payload.name.strip())
    ):
        raise HTTPException(status_code=409, detail="Curriculum board already exists")
    board = CurriculumBoard(name=payload.name.strip())
    db.add(board)
    db.flush()
    audit(db, _, "create", "board", board.id)
    db.commit()
    db.refresh(board)
    return board


@router.get("/nodes", response_model=list[CurriculumNodeResponse])
def list_nodes(
    board_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CurriculumNode]:
    return list(
        db.scalars(
            select(CurriculumNode)
            .where(CurriculumNode.board_id == board_id)
            .order_by(
                CurriculumNode.level, CurriculumNode.sequence, CurriculumNode.name
            )
        )
    )


@router.post(
    "/nodes", response_model=CurriculumNodeResponse, status_code=status.HTTP_201_CREATED
)
def create_node(
    payload: CurriculumNodeCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurriculumNode:
    require_role(_, "super_admin", "content_uploader")
    if not db.get(CurriculumBoard, payload.board_id):
        raise HTTPException(status_code=404, detail="Curriculum board not found")
    expected_parent = PARENTS[payload.level]
    parent = db.get(CurriculumNode, payload.parent_id) if payload.parent_id else None
    if expected_parent is None and payload.parent_id is not None:
        raise HTTPException(status_code=400, detail="A Class cannot have a parent")
    if expected_parent is not None and (
        not parent
        or parent.board_id != payload.board_id
        or parent.level != expected_parent
    ):
        raise HTTPException(
            status_code=400,
            detail=f"{payload.level.value} must belong to a {expected_parent.value}",
        )
    existing = db.scalar(
        select(CurriculumNode).where(
            CurriculumNode.board_id == payload.board_id,
            CurriculumNode.parent_id == payload.parent_id,
            CurriculumNode.name == payload.name.strip(),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A curriculum record with this parent and name already exists",
        )
    node = CurriculumNode(
        **payload.model_dump(exclude={"name"}), name=payload.name.strip()
    )
    db.add(node)
    db.flush()
    audit(db, _, "create", "curriculum", node.id)
    db.commit()
    db.refresh(node)
    return node
