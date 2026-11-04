from __future__ import annotations

from pathlib import Path

from readori_voicepack.cli import main
from readori_voicepack.ncref import is_non_commercial, render_nc_reference

ROOT = Path(__file__).resolve().parent.parent


def _entry(**override):
    base = {
        "id": "x-v1",
        "status": "excluded",
        "license": {"spdx": "MIT"},
        "excludedReason": "",
        "upstream": {},
    }
    base.update(override)
    return base


def test_only_excluded_non_commercial_entries_are_listed():
    assert is_non_commercial(_entry(license={"spdx": "CC-BY-NC-4.0"}))
    assert is_non_commercial(_entry(excludedReason="Non-commercial dataset (DataBaker BZNSYP)."))
    assert is_non_commercial(
        _entry(license={"spdx": "CC0", "dataset": {"spdx": "CC-BY-NC-SA-4.0"}})
    )
    assert not is_non_commercial(_entry(license={"spdx": "CC-BY-NC-4.0"}, status="approved"))
    assert not is_non_commercial(
        _entry(license={"spdx": "UNKNOWN"}, excludedReason="Voices of game characters")
    )
    assert not is_non_commercial(_entry(license={"spdx": "LicenseRef-BigScience-OpenRAIL-M"}))


def test_render_escapes_pipes_and_skips_non_https_links():
    text = render_nc_reference(
        [
            _entry(
                id="b-v1", license={"spdx": "CC-BY-NC-4.0", "url": "TODO"}, excludedReason="a | b"
            ),
            _entry(id="a-v1", license={"spdx": "CC-BY-NC-ND-4.0", "url": "https://example.org/m"}),
        ]
    )
    rows = [
        line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| id ")
    ]
    assert rows[0].startswith("| a-v1 |") and rows[0].endswith("<https://example.org/m> |")
    assert rows[1] == r"| b-v1 | CC-BY-NC-4.0 | a \| b |  |"


def test_committed_reference_is_up_to_date():
    rc = main(
        [
            "nc-reference",
            "--check",
            "--registry",
            str(ROOT / "registry" / "models.yaml"),
            "--out",
            str(ROOT / "docs" / "NC_REFERENCE.md"),
        ]
    )
    assert rc == 0
