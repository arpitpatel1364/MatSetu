from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from backend.database import get_db
from backend.models import AdminAccount
from backend.schemas.uncontested import (
    UncontestedDeclareRequest, UncontestedReverseRequest,
    UncontestedConstituencyResponse, UncontestedListResponse
)
from backend.services.uncontested import declare_uncontested, reverse_uncontested, list_uncontested
from backend.core.rls import require_role, get_current_admin
import logging

router = APIRouter(prefix="/api/v1/election", tags=["uncontested"])
logger = logging.getLogger(__name__)


@router.post("/uncontested/{constituency_id}")
async def declare_uncontested_endpoint(
    constituency_id: UUID,
    body: UncontestedDeclareRequest,
    payload: dict = Depends(require_role("T1")),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /api/v1/election/uncontested/{constituency_id}
    T1 Master + T2 State Admin 2-sign-off with TOTP.
    R1-R6 enforced in service layer.
    """
    master_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == payload["sub"])
    )
    master_admin = master_result.scalar_one_or_none()
    if not master_admin:
        raise HTTPException(status_code=401, detail="Master admin not found")

    state_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == body.state_admin_id)
    )
    state_admin = state_result.scalar_one_or_none()
    if not state_admin:
        raise HTTPException(status_code=404, detail="State admin not found")

    try:
        result = await declare_uncontested(
            db,
            constituency_id=constituency_id,
            master_admin=master_admin,
            master_admin_totp=body.master_admin_totp,
            state_admin=state_admin,
            state_admin_totp=body.state_admin_totp,
            nomination_deadline_passed=body.nomination_deadline_passed
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/uncontested/{constituency_id}")
async def reverse_uncontested_endpoint(
    constituency_id: UUID,
    body: UncontestedReverseRequest,
    payload: dict = Depends(require_role("T1")),
    db: AsyncSession = Depends(get_db)
):
    """
    DELETE /api/v1/election/uncontested/{constituency_id}
    R7: Reversal with 2-admin sign-off.
    """
    master_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == payload["sub"])
    )
    master_admin = master_result.scalar_one_or_none()

    state_result = await db.execute(
        select(AdminAccount).where(AdminAccount.id == body.state_admin_id)
    )
    state_admin = state_result.scalar_one_or_none()
    if not state_admin:
        raise HTTPException(status_code=404, detail="State admin not found")

    try:
        result = await reverse_uncontested(
            db,
            constituency_id=constituency_id,
            master_admin=master_admin,
            master_admin_totp=body.master_admin_totp,
            state_admin=state_admin,
            state_admin_totp=body.state_admin_totp,
            reason=body.reason
        )
        return result
    except (PermissionError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/uncontested", response_model=UncontestedListResponse)
async def list_uncontested_endpoint(
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4")),
    db: AsyncSession = Depends(get_db)
):
    """GET /api/v1/election/uncontested — list all uncontested seats."""
    items = await list_uncontested(db)
    return UncontestedListResponse(total=len(items), constituencies=items)


@router.get("/results/uncontested")
async def results_uncontested(
    payload: dict = Depends(require_role("T1", "T2", "T3", "T4", "T5")),
    db: AsyncSession = Depends(get_db)
):
    """
    R4/R5: Result view — UNCONTESTED badge only, no vote counts.
    """
    items = await list_uncontested(db)
    # R5: is_uncontested=TRUE flag in JSON
    for item in items:
        item["is_uncontested"] = True
        # R4: No vote count shown
        item.pop("vote_count", None)
    return {"results": items, "note": "Uncontested seats — candidate declared elected unopposed"}
