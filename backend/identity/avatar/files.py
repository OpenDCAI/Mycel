from __future__ import annotations

import io
from pathlib import Path

from backend.identity.avatar.paths import avatars_dir

AVATAR_SIZE = 256


def process_and_save_avatar(source: Path | bytes, user_id: str) -> str:
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(source)) if isinstance(source, (bytes, bytearray)) else Image.open(source)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
    storage_dir = avatars_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)
    img.save(storage_dir / f"{user_id}.png", format="PNG", optimize=True)
    return f"avatars/{user_id}.png"
