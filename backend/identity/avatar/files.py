from __future__ import annotations

import io
from pathlib import Path

from backend.identity.avatar.paths import avatars_dir

AVATAR_SIZE = 256
AVATARS_DIR = avatars_dir()


def process_and_save_avatar(source: Path | bytes, user_id: str) -> str:
    from PIL import Image, ImageOps

    if isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    img.save(AVATARS_DIR / f"{user_id}.png", format="PNG", optimize=True)
    return f"avatars/{user_id}.png"
