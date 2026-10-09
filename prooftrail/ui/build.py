"""Write the static UI to disk: pages from ``render``, assets copied unchanged."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..config import FROZEN_DIR, PROJECT_ROOT, REVIEW_DIR
from . import render
from .model import COMPARISON_PATH, Site, load_site

ASSET_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_UI_DIR = PROJECT_ROOT / "evidence" / "ui"


def page_files(site: Site) -> dict[str, str]:
    """Relative output path -> HTML for every generated page, in a stable order."""
    pages = {
        "index.html": render.render_overview(site),
        "cases.html": render.render_cases(site),
        "audit.html": render.render_new_audit(),
        "benchmark.html": render.render_benchmark(site),
        "integrations.html": render.render_integrations(),
    }
    for case in site.cases:
        pages[f"cases/{case.case_id}.html"] = render.render_case(case)
        pages[f"certificates/{case.case_id}.html"] = render.render_certificate(case)
    return pages


def build_ui(
    output_dir: Path = DEFAULT_UI_DIR,
    *,
    frozen_dir: Path = FROZEN_DIR,
    review_dir: Path = REVIEW_DIR,
    comparison_path: Path = COMPARISON_PATH,
) -> list[Path]:
    """Write every page and asset under ``output_dir``; return the files written."""
    site = load_site(frozen_dir=frozen_dir, review_dir=review_dir, comparison_path=comparison_path)
    root = Path(output_dir)
    written: list[Path] = []
    for relative, text in page_files(site).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        written.append(target)
    comparison_target = root / "benchmark.json"
    shutil.copyfile(comparison_path, comparison_target)
    written.append(comparison_target)
    for case in site.cases:
        for name in ("certificate.json", "certificate.md"):
            source = Path(frozen_dir) / case.case_id / name
            target = root / "certificates" / f"{case.case_id}.{name.rsplit('.', 1)[1]}"
            shutil.copyfile(source, target)
            written.append(target)
    for source in sorted(ASSET_DIR.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        target = root / "assets" / source.relative_to(ASSET_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)
    return written
