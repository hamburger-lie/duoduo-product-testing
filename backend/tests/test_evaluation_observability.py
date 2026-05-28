from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy import select

from app.core.logging import JsonFormatter
from app.db.models.persona import Persona
from app.db.models.survey import Survey
from app.services.evaluation_service import EvaluationService
from app.tasks.evaluation_tasks import _run_evaluation_async
from tests.test_evaluation_survey import (
    EvaluationSurveyContext,
    login,
    prepare_runnable_evaluation,
)
from tests.test_evaluation_tasks import TaskContext, create_task_fixture

pytest_plugins = (
    "tests.test_evaluation_survey",
    "tests.test_evaluation_tasks",
)


def test_json_formatter_includes_evaluation_observability_fields() -> None:
    record = logging.LogRecord(
        name="tests.evaluation",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="evaluation event",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.user_id = 7
    record.evaluation_id = 11
    record.task_id = "task-abc"
    record.persona_id = 13
    record.event = "evaluation_persona_finished"
    record.from_status = "answering"
    record.to_status = "done"
    record.duration_ms = 42
    record.error_code = "AI_SERVICE_TIMEOUT"
    record.provider = "ark"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == 7
    assert payload["evaluation_id"] == 11
    assert payload["task_id"] == "task-abc"
    assert payload["persona_id"] == 13
    assert payload["event"] == "evaluation_persona_finished"
    assert payload["from_status"] == "answering"
    assert payload["to_status"] == "done"
    assert payload["duration_ms"] == 42
    assert payload["error_code"] == "AI_SERVICE_TIMEOUT"
    assert payload["provider"] == "ark"


async def test_run_and_cancel_emit_correlated_evaluation_logs(
    evaluation_survey_context: EvaluationSurveyContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_observability")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )

    with caplog.at_level(logging.INFO):
        run_response = await evaluation_survey_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/run",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": "req-observability-run",
            },
        )
        cancel_response = await evaluation_survey_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/cancel",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": "req-observability-cancel",
            },
        )

    assert run_response.status_code == 202
    assert cancel_response.status_code == 409
    run_records = [record for record in caplog.records if record.msg == "evaluation_run_requested"]
    assert len(run_records) == 1
    assert run_records[0].evaluation_id == int(evaluation_id)
    assert run_records[0].request_id == "req-observability-run"
    assert run_records[0].user_id


async def test_task_logs_persona_failure_and_finalize_context(
    task_context: TaskContext,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    evaluation_id, user_id, persona_id = await create_task_fixture(task_context)

    async def fake_generate_answer(*args: object, **kwargs: object) -> tuple[list[dict], int, str]:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        "app.services.evaluation_service.EvaluationService._generate_answer",
        fake_generate_answer,
    )

    with caplog.at_level(logging.INFO):
        result = await _run_evaluation_async(evaluation_id, user_id, "celery-task-id")

    assert result["status"] == "failed"
    persona_failed = [
        record for record in caplog.records if record.msg == "evaluation_persona_failed"
    ]
    finalized = [record for record in caplog.records if record.msg == "evaluation_finalized"]
    assert len(persona_failed) == 1
    assert persona_failed[0].evaluation_id == evaluation_id
    assert persona_failed[0].task_id == "celery-task-id"
    assert persona_failed[0].persona_id == persona_id
    assert persona_failed[0].error_message == "model unavailable"
    assert len(finalized) == 1
    assert finalized[0].evaluation_id == evaluation_id
    assert finalized[0].task_id == "celery-task-id"
    assert finalized[0].to_status == "failed"


async def test_ai_fallback_log_includes_evaluation_and_provider_context(
    task_context: TaskContext,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    evaluation_id, _, persona_id = await create_task_fixture(task_context)
    monkeypatch.setenv("AI_PROVIDER", "ark")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        async with task_context.session_factory() as session:
            survey = await session.scalar(
                select(Survey).where(Survey.evaluation_id == evaluation_id)
            )
            persona = await session.get(Persona, persona_id)
            assert survey is not None
            assert persona is not None

            async def fake_generate_answer_with_ai(*args: object, **kwargs: object) -> object:
                raise RuntimeError("provider timeout")

            monkeypatch.setattr(
                EvaluationService,
                "_generate_answer_with_ai_usage",
                fake_generate_answer_with_ai,
            )

            with caplog.at_level(logging.ERROR):
                await EvaluationService(session)._generate_answer(
                    survey=survey,
                    persona=persona,
                    product_summary={"id": 1},
                )
    finally:
        get_settings.cache_clear()

    fallback_records = [
        record for record in caplog.records if record.msg == "persona_answer_ai_failed"
    ]
    assert len(fallback_records) == 1
    assert fallback_records[0].evaluation_id == evaluation_id
    assert fallback_records[0].persona_id == persona_id
    assert fallback_records[0].provider == "ark"
    assert fallback_records[0].error_message == "provider timeout"
