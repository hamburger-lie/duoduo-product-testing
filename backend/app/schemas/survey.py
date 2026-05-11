from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionType = Literal["single", "multi", "scale_1_5", "open"]


class SurveyGenerateRequest(BaseModel):
    """Generate survey request."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    evaluation_id: str
    extra_focus: str | None = Field(default=None, max_length=200)


class SurveyQuestion(BaseModel):
    """Survey question shape from the API contract."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=32)
    dim: str = Field(min_length=1, max_length=64)
    type: QuestionType
    question: str = Field(min_length=1, max_length=500)
    options: list[str] | None = None

    @model_validator(mode="after")
    def validate_options(self) -> SurveyQuestion:
        if self.type in {"single", "multi"} and not self.options:
            raise ValueError("single and multi questions require non-empty options")
        return self


class SurveyResponse(BaseModel):
    """Survey response aligned to the API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    evaluation_id: str
    product_id: str
    version: int
    generated_by: str
    questions: list[SurveyQuestion]
    created_at: str
