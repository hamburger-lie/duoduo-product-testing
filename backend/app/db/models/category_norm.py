from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonDict

if TYPE_CHECKING:
    from app.db.models.evaluation import Evaluation
    from app.db.models.product import Product


class CategoryNorm(Base, BaseModelMixin):
    """品类常模池条目：每个完成的评测在此留下一条聚合分数。

    用途：新品报告不再只看绝对分，而是对比同品类历史分布输出百分位
    （norm-referenced scoring，参照传统概念测试的品类常模做法）。
    数据为全平台共享的聚合值，不含答案明细。
    """

    __tablename__ = "category_norms"
    __table_args__ = (
        Index("ix_category_norms_category", "category"),
        Index("ix_category_norms_evaluation_id", "evaluation_id", unique=True),
    )

    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent_avg: Mapped[float] = mapped_column(Float, nullable=False)
    intent_distribution: Mapped[JsonDict] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 预留：标记该条目来自公认畅销品/基准品的对照评测（后续「基准品对照」功能使用）
    is_benchmark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    evaluation: Mapped["Evaluation"] = relationship()
    product: Mapped["Product"] = relationship()
