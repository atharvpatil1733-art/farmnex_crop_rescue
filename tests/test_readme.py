"""The README must state the same numbers, source and assumptions the code uses."""

from __future__ import annotations

import json
from pathlib import Path

from crop_rescue.config import Settings

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_cites_the_source():
    assert "Handbook 66" in README
    assert "Hardenburg" in README
    assert "https://extension.umaine.edu/publications/4135e/" in README


def test_readme_lists_every_assumption_with_its_current_default():
    s = Settings(_env_file=None)
    for text in (
        "**Q10**",
        "**Default temperature**",
        "**Demo buyers**",
        "**Transport cost**",
        "**Average speed**",
        f"₹{s.transport_rs_per_km:g} per km",
        f"{s.avg_speed_kmph:g} km/h",
        f"{s.default_temp_c:g} °C",
        f"{s.loading_hours:g} hours",
        f"{s.road_factor:g}",
        f"{s.radius_km:g} km",
        "`CR_Q10`",
    ):
        assert text in README, text
    assert f"| {s.q10:.1f} |" in README


def test_readme_names_all_eight_crops_and_the_limitations():
    data = json.loads((ROOT / "crop_rescue" / "data" / "crops.json").read_text(encoding="utf-8"))
    codes = [c["code"] for c in data["crops"]]
    assert len(codes) == 8
    for code in codes:
        assert code in README, code
    assert "48 + 12" in README
    assert "labrusca" in README


def test_readme_has_the_five_step_demo_and_links_the_transcript():
    for n in range(1, 6):
        assert f"\n{n}. **" in README, n
    assert "docs/demo_transcript.md" in README
