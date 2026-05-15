from __future__ import annotations

import json

from scripts import seed_personas


def test_load_persona_seed_files_prefers_personas_v2(
    tmp_path,
    monkeypatch,
) -> None:
    seeds_root = tmp_path / "SEEDS"
    legacy_dir = seeds_root / "personas"
    v2_dir = seeds_root / "personas_v2"
    legacy_dir.mkdir(parents=True)
    v2_dir.mkdir()
    (legacy_dir / "legacy.json").write_text(
        json.dumps({"name": "旧角色", "profile": {"bio": "legacy"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (v2_dir / "v2.json").write_text(
        json.dumps(
            {
                "name": "新角色",
                "profile": {
                    "bio": "v2",
                    "mind_model": ["先看证据"],
                    "honest_boundaries": ["不能假装真实使用"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(seed_personas, "PERSONA_SEEDS_ROOT", legacy_dir)
    monkeypatch.setattr(seed_personas, "PERSONA_V2_SEEDS_ROOT", v2_dir)

    seeds = seed_personas.load_persona_seed_files()

    assert [seed["name"] for seed in seeds] == ["新角色"]
    assert seeds[0]["profile"]["mind_model"] == ["先看证据"]


def test_load_persona_seed_files_falls_back_to_legacy_personas(
    tmp_path,
    monkeypatch,
) -> None:
    seeds_root = tmp_path / "SEEDS"
    legacy_dir = seeds_root / "personas"
    v2_dir = seeds_root / "personas_v2"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "legacy.json").write_text(
        json.dumps({"name": "旧角色", "profile": {"bio": "legacy"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(seed_personas, "PERSONA_SEEDS_ROOT", legacy_dir)
    monkeypatch.setattr(seed_personas, "PERSONA_V2_SEEDS_ROOT", v2_dir)

    seeds = seed_personas.load_persona_seed_files()

    assert [seed["name"] for seed in seeds] == ["旧角色"]
