from __future__ import annotations

from fastapi import APIRouter, Query

from core.context import LocationSearchScope, search_locations

router = APIRouter(tags=["locations"])


@router.get("/locations/search")
async def location_search(
    q: str = Query(..., min_length=1, max_length=60, description="locationtranslated"),
    limit: int = Query(default=8, ge=1, le=10, description="translated"),
    scope: LocationSearchScope = Query(default="auto", description="translated：auto/cn/global"),
    locale: str = Query(default="en", description="Result language: zh/en/hr"),
):
    query = q.strip()
    if not query:
        return {"query": "", "items": []}
    items = await search_locations(query, limit=limit, scope=scope, locale=locale)
    return {"query": query, "scope": scope, "locale": locale, "items": items}
