from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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


class DailyLoginCreditResponse(BaseModel):
    """Response for claiming the daily login credit reward."""

    model_config = ConfigDict(extra="forbid")

    awarded: bool
    amount: int
    balance: int
