from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.rate_limit import IPRateLimiter, RateLimiter
from app.core.security import get_current_user
from app.db.models.customize_request import CustomizeRequest as CustomizeRequestModel
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/customize", tags=["customize"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
customize_rate_limit_dependency = Depends(RateLimiter("customize"))
customize_ip_rate_limit_dependency = Depends(IPRateLimiter(limit=10, window=60))


class CustomizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=1, max_length=64)
    company: str = Field(min_length=1, max_length=100)
    requirement: str = Field(min_length=1, max_length=2000)


@router.post("/submit")
async def submit_customize(
    request: Request,
    body: CustomizeRequest,
    _user_rl: None = customize_rate_limit_dependency,
    _ip_rl: None = customize_ip_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> dict:
    client_ip = (request.client.host if request.client else None) or None
    row = CustomizeRequestModel(
        user_id=current_user.id,
        name=body.name.strip(),
        phone=body.phone.strip(),
        company=body.company.strip(),
        requirement=body.requirement.strip(),
        ip=client_ip,
        user_agent=request.headers.get("User-Agent"),
        status="submitted",
    )
    session.add(row)
    await session.commit()
    return {"ok": True}
