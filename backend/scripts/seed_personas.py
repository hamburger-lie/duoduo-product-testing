from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import load_all_models
from app.db.repositories.persona import PersonaRepository
from app.db.session import AsyncSessionFactory

load_all_models()

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
SEEDS_ROOT = PROJECT_ROOT / "docs" / "SEEDS"
PERSONA_SEEDS_ROOT = SEEDS_ROOT / "personas"
SURVEY_TEMPLATE_PATH = SEEDS_ROOT / "survey_templates" / "beauty_survey_template.json"
REPORT_TEMPLATE_PATH = SEEDS_ROOT / "report_templates" / "beauty_report_template.json"


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON seed file."""

    return json.loads(path.read_text(encoding="utf-8"))


def load_persona_seed_files() -> list[dict[str, Any]]:
    """Load persona seed JSON files from docs/SEEDS."""

    return [load_json_file(path) for path in sorted(PERSONA_SEEDS_ROOT.glob("*.json"))]


def load_template_seed_files() -> dict[str, dict[str, Any]]:
    """Load survey and report template JSON files for future import work."""

    return {
        "survey": load_json_file(SURVEY_TEMPLATE_PATH),
        "report": load_json_file(REPORT_TEMPLATE_PATH),
    }


def build_persona_values(seed: dict[str, Any]) -> dict[str, Any]:
    """Map a persona seed document to ORM values."""

    ocean = seed.get("ocean", {})
    return {
        "owner_id": None,
        "name": seed["name"],
        "avatar": seed.get("avatar"),
        "age": seed["age"],
        "gender": seed["gender"],
        "city": seed["city"],
        "city_tier": seed.get("city_tier"),
        "occupation": seed.get("occupation"),
        "income_monthly": seed.get("income_monthly"),
        "ocean_o": ocean.get("o"),
        "ocean_c": ocean.get("c"),
        "ocean_e": ocean.get("e"),
        "ocean_a": ocean.get("a"),
        "ocean_n": ocean.get("n"),
        "persona_tag": seed.get("persona_tag"),
        "profile": seed["profile"],
        "categories": seed.get("categories", []),
        "is_critical": seed.get("is_critical", False),
        "version": 1,
        "status": "active",
    }


async def upsert_personas(session: AsyncSession, seeds: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert or update persona seeds by name + version."""

    repository = PersonaRepository(session)
    created_count = 0
    updated_count = 0

    for seed in seeds:
        values = build_persona_values(seed)
        existing = await repository.get_by_name_and_version(
            name=values["name"],
            version=values["version"],
        )
        if existing is None:
            await repository.create(values)
            created_count += 1
        else:
            await repository.update(existing, values)
            updated_count += 1

    return created_count, updated_count


async def run_seed() -> tuple[int, int]:
    """Run persona seeding and return created/updated counts."""

    seeds = load_persona_seed_files()
    load_template_seed_files()

    async with AsyncSessionFactory() as session:
        async with session.begin():
            return await upsert_personas(session, seeds)


def parse_args() -> argparse.Namespace:
    """Parse script arguments."""

    parser = argparse.ArgumentParser(description="Seed system personas from docs/SEEDS.")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    parse_args()
    created_count, updated_count = asyncio.run(run_seed())
    print(f"persona seeds applied: created={created_count}, updated={updated_count}")
    print(
        "template seeds read: "
        "survey=beauty_survey_template_v0_1, report=beauty_report_template_v0_1"
    )
    print("template import TODO: no dedicated template table exists in TECH_DESIGN.md")


if __name__ == "__main__":
    main()
