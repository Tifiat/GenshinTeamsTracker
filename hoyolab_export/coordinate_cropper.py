import json
from pathlib import Path
from typing import Any

from PIL import Image


def scaled_box(rect: dict[str, float], scale: float) -> tuple[int, int, int, int]:
    left = round(rect["left"] * scale)
    top = round(rect["top"] * scale)
    right = round(rect["right"] * scale)
    bottom = round(rect["bottom"] * scale)
    return left, top, right, bottom


def crop_from_layout(
    image_path: str | Path,
    layout_path: str | Path,
    output_dir: str | Path,
    scale: float,
) -> list[dict[str, Any]]:
    """Crop DOM-described regions from the final HoYoLAB image.

    The expected layout shape is intentionally small for the next iteration:
    {"items": [{"id": "...", "kind": "character|weapon", "rect": {...}}]}.
    """
    image_path = Path(image_path)
    layout_path = Path(layout_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    items = layout.get("items", [])
    manifest: list[dict[str, Any]] = []

    with Image.open(image_path) as image:
        for index, item in enumerate(items):
            rect = item.get("rect")
            if not isinstance(rect, dict):
                continue

            kind = item.get("kind") or "item"
            crop_dir = output_dir / f"{kind}s"
            crop_dir.mkdir(parents=True, exist_ok=True)

            crop_path = crop_dir / f"{kind}_{index:03}.png"
            image.crop(scaled_box(rect, scale)).save(crop_path)

            manifest.append(
                {
                    "source_id": item.get("id"),
                    "kind": kind,
                    "rect": rect,
                    "scale": scale,
                    "crop": str(crop_path.relative_to(output_dir)),
                }
            )

    (output_dir / "crop_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
