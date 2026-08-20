from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


async def paginate(session: AsyncSession, query: Select, *, limit: int, offset: int) -> tuple[list, int]:
    """Runs `query` twice — once wrapped in COUNT(*) for the total (over
    whatever filters the caller already applied, before slicing), once
    with LIMIT/OFFSET for the page itself. Two round-trips, not a window
    function: simpler, more portable, and list endpoints here aren't hot
    paths. `query` should already have any domain-specific filters
    (.where(), .join()) applied — this only adds counting and slicing."""
    total = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await session.execute(query.limit(limit).offset(offset))
    return list(result.scalars().all()), total
