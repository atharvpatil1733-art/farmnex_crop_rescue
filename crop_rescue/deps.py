"""Who is the farmer.

The router never trusts the request body for identity. Every farmer-facing
endpoint gets the farmer id from `Depends(current_farmer_id)`. The host
overrides this one dependency with its own login check:

    app.dependency_overrides[crop_rescue.current_farmer_id] = (
        lambda user=Depends(get_current_user): str(user.id)
    )

After that, the `?farmer_id=` query parameter below is ignored and the
farmer is always the logged-in user. Without an override (local dev only),
`?farmer_id=` lets you test as different farmers by hand.
"""

from __future__ import annotations

from fastapi import HTTPException, Query


def current_farmer_id(
    farmer_id: str | None = Query(
        None, description="Dev/demo only. The host overrides this with the logged-in user."
    ),
) -> str:
    """The current farmer's id. 401 if no farmer could be identified."""
    if not farmer_id:
        raise HTTPException(status_code=401, detail="Farmer not identified")
    return farmer_id
