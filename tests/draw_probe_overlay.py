import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "tests" / "probe_layout_output"


def latest_probe_dir() -> Path:
    dirs = [p for p in OUTPUT_ROOT.iterdir() if p.is_dir()]
    if not dirs:
        raise SystemExit("No probe_layout_output folders found")
    return max(dirs, key=lambda p: p.stat().st_mtime)


def pick_image(folder: Path) -> Path:
    images = [
        p for p in folder.glob("*.png")
        if p.name not in {"page_screenshot.png", "exported_image_overlay.png"}
        and not p.name.endswith("_overlay.png")
    ]
    if not images:
        raise SystemExit("No exported PNG found")
    return max(images, key=lambda p: Image.open(p).size[0] * Image.open(p).size[1])


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_probe_dir()
    probe_path = folder / "layout_probe.json"
    if not probe_path.exists():
        raise SystemExit(f"Missing {probe_path}")

    probe = json.loads(probe_path.read_text(encoding="utf-8"))

    image_path = pick_image(folder)
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    root_probe = probe.get("html2canvasRootProbe") or {}
    root_rect = root_probe.get("rootRect") or {}
    options = root_probe.get("html2canvasOptions") or {}

    scale = options.get("scale") or (probe.get("exporter") or {}).get("scale") or 4
    canvas_css_width = (
        options.get("width")
        or options.get("windowWidth")
        or (probe.get("exporter") or {}).get("fixedContainerWidth")
        or image.size[0] / scale
    )
    root_width = root_rect.get("width") or canvas_css_width
    x_offset_css = 0

    image_like = ((probe.get("rootDiscovery") or {}).get("imageLike") or [])[:120]

    for item in image_like:
        rect = item.get("rect_root_relative")
        if not rect:
            continue

        left = int(round(rect["left"] * scale))
        top = int(round(rect["top"] * scale))
        right = int(round(rect["right"] * scale))
        bottom = int(round(rect["bottom"] * scale))

        if right < 0 or bottom < 0 or left > image.size[0] or top > image.size[1]:
            continue

        draw.rectangle((left, top, right, bottom), outline=(255, 0, 0), width=3)
        draw.text((left + 3, top + 3), str(item.get("index")), fill=(255, 0, 0))

    summary = {
        "folder": str(folder),
        "image": image_path.name,
        "image_size": image.size,
        "scale": scale,
        "canvas_css_width": canvas_css_width,
        "root_width": root_width,
        "x_offset_css": x_offset_css,
        "root_rect": root_rect,
        "image_like_count": len((probe.get("rootDiscovery") or {}).get("imageLike") or []),
        "drawn_count": len(image_like),
    }

    out_image = folder / "exported_image_overlay.png"
    out_json = folder / "overlay_summary.json"

    image.save(out_image)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("folder:", folder)
    print("image:", image_path.name, image.size)
    print("scale:", scale)
    print("canvas_css_width:", canvas_css_width)
    print("root_width:", root_width)
    print("x_offset_css:", x_offset_css)
    print("image_like_count:", summary["image_like_count"])
    print("created:", out_image)
    print("created:", out_json)


if __name__ == "__main__":
    main()