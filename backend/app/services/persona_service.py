from __future__ import annotations

from datetime import UTC
from math import ceil
from typing import Literal

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.persona import Persona
from app.db.models.user import User
from app.db.repositories.persona import PersonaRepository
from app.db.repositories.product import ProductRepository
from app.schemas.persona import (
    OceanScores,
    PersonaCreateRequest,
    PersonaListItem,
    PersonaPageResponse,
    PersonaResponse,
    PersonaUpdateRequest,
)

OwnerScope = Literal["system", "mine", "all"]

PROFILE_REQUIRED_KEYS = {
    "bio",
    "shopping_habits",
    "skincare_concerns",
    "brand_preferences",
    "price_sensitivity",
    "info_channels",
    "decision_style",
    "pet_phrases",
    "pain_points",
    "lifestyle",
}


class PersonaService:
    """Persona use cases without external persona-hub or LLM integrations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.personas = PersonaRepository(session)
        self.products = ProductRepository(session)

    async def list_personas(
        self,
        *,
        user: User,
        category: str | None,
        page: int,
        page_size: int,
        include_critical: bool,
        owner_scope: OwnerScope,
        keyword: str | None,
    ) -> PersonaPageResponse:
        """List personas visible to the current user."""

        personas = await self.personas.list_visible_to_user(user_id=user.id)
        filtered = self._filter_personas(
            personas,
            user=user,
            category=category,
            include_critical=include_critical,
            owner_scope=owner_scope,
            keyword=keyword,
        )
        return self._page_response(personas=filtered, page=page, page_size=page_size)

    async def recommend_personas(
        self,
        *,
        user: User,
        product_id: int,
        count: int,
    ) -> PersonaPageResponse:
        """Recommend visible personas by product category with critical-user balance."""

        product = await self.products.get_by_id_and_user_id(product_id=product_id, user_id=user.id)
        if product is None:
            raise self._product_not_found(product_id)

        visible_personas = await self.personas.list_visible_to_user(user_id=user.id)
        category = product.category
        matched = [
            persona
            for persona in visible_personas
            if category is not None and category in self._categories(persona)
        ]
        unmatched = [persona for persona in visible_personas if persona not in matched]
        ordered = matched + unmatched
        selected = self._ensure_critical_balance(ordered, count=count)
        return self._page_response(personas=selected, page=1, page_size=count)

    async def get_persona(self, *, user: User, persona_id: int) -> PersonaResponse:
        """Return a full persona visible to the current user."""

        persona = await self.personas.get_active_by_id(persona_id=persona_id)
        if persona is None or not self._can_read(user=user, persona=persona):
            raise self._persona_not_found(persona_id)
        return self._to_response(persona)

    async def create_persona(
        self,
        *,
        user: User,
        payload: PersonaCreateRequest,
    ) -> PersonaResponse:
        """Create a private persona owned by the current user."""

        self._validate_profile(payload.profile)
        persona = await self.personas.create(
            {
                "owner_id": user.id,
                "name": payload.name,
                "avatar": payload.avatar,
                "age": payload.age,
                "gender": payload.gender,
                "city": payload.city,
                "city_tier": None,
                "occupation": payload.occupation,
                "income_monthly": payload.income_monthly,
                "ocean_o": payload.ocean.o,
                "ocean_c": payload.ocean.c,
                "ocean_e": payload.ocean.e,
                "ocean_a": payload.ocean.a,
                "ocean_n": payload.ocean.n,
                "persona_tag": payload.persona_tag,
                "profile": payload.profile,
                "categories": payload.categories,
                "is_critical": payload.is_critical,
                "version": 1,
                "status": "active",
            }
        )
        await self.session.commit()
        return self._to_response(persona)

    async def update_persona(
        self,
        *,
        user: User,
        persona_id: int,
        payload: PersonaUpdateRequest,
    ) -> PersonaResponse:
        """Update a private persona owned by the current user."""

        persona = await self._get_owned_private_persona(user=user, persona_id=persona_id)
        values = payload.model_dump(exclude_unset=True, exclude={"ocean"})
        if "profile" in values:
            self._validate_profile(values["profile"])
        if payload.ocean is not None:
            values.update(
                {
                    "ocean_o": payload.ocean.o,
                    "ocean_c": payload.ocean.c,
                    "ocean_e": payload.ocean.e,
                    "ocean_a": payload.ocean.a,
                    "ocean_n": payload.ocean.n,
                }
            )
        await self.personas.update(persona, values)
        await self.session.commit()
        return self._to_response(persona)

    async def delete_persona(self, *, user: User, persona_id: int) -> None:
        """Soft-delete a private persona owned by the current user."""

        persona = await self._get_owned_private_persona(user=user, persona_id=persona_id)
        await self.personas.soft_delete(persona)
        await self.session.commit()

    async def _get_owned_private_persona(self, *, user: User, persona_id: int) -> Persona:
        persona = await self.personas.get_active_by_id(persona_id=persona_id)
        if persona is None:
            raise self._persona_not_found(persona_id)
        if persona.owner_id != user.id:
            raise self._persona_not_owned(persona_id)
        return persona

    def _filter_personas(
        self,
        personas: list[Persona],
        *,
        user: User,
        category: str | None,
        include_critical: bool,
        owner_scope: OwnerScope,
        keyword: str | None,
    ) -> list[Persona]:
        filtered = [
            persona
            for persona in personas
            if self._matches_owner_scope(persona=persona, user=user, owner_scope=owner_scope)
        ]
        if category:
            filtered = [persona for persona in filtered if category in self._categories(persona)]
        if not include_critical:
            filtered = [persona for persona in filtered if not persona.is_critical]
        if keyword:
            normalized = keyword.lower()
            filtered = [
                persona
                for persona in filtered
                if normalized in persona.name.lower()
                or normalized in (persona.persona_tag or "").lower()
            ]
        return filtered

    def _matches_owner_scope(
        self,
        *,
        persona: Persona,
        user: User,
        owner_scope: OwnerScope,
    ) -> bool:
        if owner_scope == "system":
            return persona.owner_id is None
        if owner_scope == "mine":
            return persona.owner_id == user.id
        return persona.owner_id is None or persona.owner_id == user.id

    def _ensure_critical_balance(self, personas: list[Persona], *, count: int) -> list[Persona]:
        selected = personas[:count]
        required_critical = max(1, ceil(count * 0.2))
        current_critical = sum(1 for persona in selected if persona.is_critical)
        if current_critical >= required_critical:
            return selected

        selected_ids = {persona.id for persona in selected}
        critical_candidates = [
            persona
            for persona in personas
            if persona.is_critical and persona.id not in selected_ids
        ]
        for candidate in critical_candidates[: required_critical - current_critical]:
            if len(selected) >= count:
                selected[-1] = candidate
            else:
                selected.append(candidate)
        return selected

    def _page_response(
        self,
        *,
        personas: list[Persona],
        page: int,
        page_size: int,
    ) -> PersonaPageResponse:
        offset = (page - 1) * page_size
        page_items = personas[offset : offset + page_size]
        total = len(personas)
        return PersonaPageResponse(
            items=[self._to_list_item(persona) for persona in page_items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def _validate_profile(self, profile: dict[str, object]) -> None:
        missing_keys = sorted(PROFILE_REQUIRED_KEYS.difference(profile.keys()))
        if missing_keys:
            raise AppException(
                code="PERSONA_PROFILE_INVALID",
                message="Persona profile is missing required fields",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"missing_keys": missing_keys},
            )

    def _can_read(self, *, user: User, persona: Persona) -> bool:
        return persona.owner_id is None or persona.owner_id == user.id

    def _categories(self, persona: Persona) -> list[str]:
        return [str(category) for category in (persona.categories or [])]

    def _to_list_item(self, persona: Persona) -> PersonaListItem:
        return PersonaListItem(
            id=str(persona.id),
            name=persona.name,
            avatar=persona.avatar,
            age=persona.age,
            gender=persona.gender,
            city=persona.city,
            city_tier=persona.city_tier,
            occupation=persona.occupation,
            income_monthly=persona.income_monthly,
            persona_tag=persona.persona_tag,
            categories=self._categories(persona),
            is_critical=persona.is_critical,
            is_system=persona.owner_id is None,
        )

    def _to_response(self, persona: Persona) -> PersonaResponse:
        item = self._to_list_item(persona)
        return PersonaResponse(
            **item.model_dump(),
            ocean=OceanScores(
                o=persona.ocean_o or 0,
                c=persona.ocean_c or 0,
                e=persona.ocean_e or 0,
                a=persona.ocean_a or 0,
                n=persona.ocean_n or 0,
            ),
            profile=dict(persona.profile or {}),
            version=persona.version,
            created_at=persona.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )

    def _persona_not_found(self, persona_id: int) -> AppException:
        return AppException(
            code="PERSONA_NOT_FOUND",
            message="Persona not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"persona_id": str(persona_id)},
        )

    def _persona_not_owned(self, persona_id: int) -> AppException:
        return AppException(
            code="PERSONA_NOT_OWNED",
            message="Persona is not owned by current user",
            http_status=status.HTTP_403_FORBIDDEN,
            details={"persona_id": str(persona_id)},
        )

    def _product_not_found(self, product_id: int) -> AppException:
        return AppException(
            code="PRODUCT_NOT_FOUND",
            message="Product not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"product_id": str(product_id)},
        )
