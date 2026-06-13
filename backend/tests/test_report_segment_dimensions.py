"""Unit tests for the real per-segment per-dimension heatmap aggregation."""
from __future__ import annotations

from typing import Any

from app.services.report_service import ReportService


def _svc() -> ReportService:
    return ReportService.__new__(ReportService)


def _answer(persona_id: int, intent: int | None, items: list[dict[str, Any]]) -> Any:
    class _A:
        pass

    a = _A()
    a.persona_id = persona_id
    a.overall_intent = intent
    a.answers = items
    return a


def _persona(pid: int, tag: str) -> Any:
    class _P:
        pass

    p = _P()
    p.persona_id = pid
    p.persona_tag = tag
    return p


QID_TO_DIM = {"q01": "first_impression", "q07": "price_sensitivity"}


def test_segment_dimensions_real_scale_averages() -> None:
    answers = [
        _answer(1, 4, [
            {"qid": "q01", "type": "scale_1_5", "answer": 4},
            {"qid": "q01", "type": "scale_1_5", "answer": 5},
        ]),
        _answer(2, 2, [{"qid": "q01", "type": "scale_1_5", "answer": 2}]),
    ]
    personas = {1: _persona(1, "宝妈"), 2: _persona(2, "蓝领")}
    out = _svc()._calc_segment_dimensions(answers, personas, QID_TO_DIM)

    by_seg = {item.segment: item for item in out}
    assert by_seg["宝妈"].dims["first_impression"] == 4.5
    assert by_seg["蓝领"].dims["first_impression"] == 2.0
    assert by_seg["宝妈"].count == 1


def test_segment_dimensions_fallback_to_intent_then_null() -> None:
    # 宝妈 has no scale answers at all → every dim falls back to intent avg 3.0
    answers = [_answer(1, 3, [{"qid": "q99", "type": "open", "answer": "不错"}])]
    personas = {1: _persona(1, "宝妈")}
    out = _svc()._calc_segment_dimensions(answers, personas, QID_TO_DIM)
    assert out[0].dims["price_sensitivity"] == 3.0

    # No intent either → null, never fabricated
    answers2 = [_answer(1, None, [])]
    out2 = _svc()._calc_segment_dimensions(answers2, personas, QID_TO_DIM)
    assert out2[0].dims["package_appearance"] is None


def test_segment_dimensions_ignores_non_scale_and_unknown_dims() -> None:
    answers = [
        _answer(1, 5, [
            {"qid": "q01", "type": "open", "answer": "5"},  # open 不计入
            {"qid": "q88", "type": "scale_1_5", "answer": 1},  # 未知 qid 不计入
        ]),
    ]
    personas = {1: _persona(1, "银发")}
    out = _svc()._calc_segment_dimensions(answers, personas, QID_TO_DIM)
    # 没有有效 scale 命中 → 回退 intent 5.0
    assert out[0].dims["first_impression"] == 5.0
