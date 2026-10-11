import os
import secrets

from fastapi import Header, HTTPException


def require_demo_key(x_demo_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("DEMO_KEY")
    if not expected:
        return  # local development: no key configured
    if not x_demo_key or not secrets.compare_digest(x_demo_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid demo key")
