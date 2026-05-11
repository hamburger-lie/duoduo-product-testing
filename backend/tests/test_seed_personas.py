from __future__ import annotations

from scripts.seed_personas import (
    build_persona_values,
    load_persona_seed_files,
    load_template_seed_files,
)


def test_persona_seed_files_load_from_docs_seed_directory() -> None:
    seeds = load_persona_seed_files()

    assert len(seeds) == 5
    assert {seed["seed_key"] for seed in seeds} >= {"persona_beauty_001", "persona_beauty_005"}


def test_persona_seed_mapping_uses_name_and_version_for_idempotency() -> None:
    seed = load_persona_seed_files()[0]
    values = build_persona_values(seed)

    assert values["name"] == seed["name"]
    assert values["version"] == 1
    assert values["profile"] == seed["profile"]
    assert values["categories"] == seed["categories"]


def test_template_seed_files_are_read_for_future_import() -> None:
    templates = load_template_seed_files()

    assert templates["survey"]["template_key"] == "beauty_survey_template_v0_1"
    assert templates["report"]["template_key"] == "beauty_report_template_v0_1"
