"""Generate N users + signed JWT tokens for load testing (bypasses login rate-limit).

Run inside the api container:
    docker exec -e PYTHONPATH=/app -w /app duoduo-api uv run python scripts/gen_loadtest_tokens.py
Outputs /app/loadtest_tokens.json (a JSON array of bearer tokens).
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import load_all_models
from app.db.models.user import User
from app.db.session import AsyncSessionFactory

N = 250  # a bit more than 200 so locust users each get a distinct token
OUT_PATH = "/app/loadtest_tokens.json"


async def main() -> None:
    load_all_models()
    tokens: list[str] = []
    async with AsyncSessionFactory() as session:
        async with session.begin():
            for i in range(N):
                openid = f"loadtest_user_{i:04d}"
                existing = (
                    await session.execute(select(User).where(User.openid == openid))
                ).scalar_one_or_none()
                if existing is None:
                    user = User(
                        openid=openid,
                        nickname=f"load{i}",
                        credit_balance=1_000_000,  # plenty so write-ops don't run out
                    )
                    session.add(user)
                    await session.flush()  # assign user.id
                else:
                    user = existing
                token, _ = create_access_token(user_id=user.id)
                tokens.append(token)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f)
    print(f"generated {len(tokens)} tokens -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
