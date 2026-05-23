from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreditBalanceResponse(BaseModel):
    """Response for GET /credits/balance."""

    model_config = ConfigDict(extra="forbid")

    balance: int
    updated_at: str  # ISO 8601 UTC


class CreditTransactionItem(BaseModel):
    """One credit transaction row."""

    model_config = ConfigDict(extra="forbid")

    id: str
    amount: int  # negative = deduction, positive = credit
    balance_after: int | None
    # init | survey_gen | persona_answer | chat | recharge | refund | manual_adjust
    reason: str | None
    ref_type: str | None  # evaluation | conversation | …
    ref_id: str | None  # stringified ref id
    note: str | None
    created_at: str  # ISO 8601 UTC


class CreditTransactionListResponse(BaseModel):
    """Cursor-paginated credit transaction list."""

    model_config = ConfigDict(extra="forbid")

    items: list[CreditTransactionItem]
    next_cursor: str | None
    has_more: bool


class CreditRechargeRequest(BaseModel):
    """Create a pending recharge order."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amount_yuan: Decimal = Field(gt=Decimal("0.00"), max_digits=10, decimal_places=2)
    credits: int = Field(gt=0, le=1_000_000)
    provider: Literal["manual"] = "manual"


class CreditRechargeResponse(BaseModel):
    """Recharge order response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    order_no: str
    provider: str
    amount_yuan: Decimal
    credits: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None


class CreditRechargeCallbackRequest(BaseModel):
    """Signed internal recharge settlement callback."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_no: str
    provider_transaction_id: str
    paid_at: datetime | None = None
