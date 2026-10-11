"""Regression tests for the dashboard's alert classification (docs/index.html).

The page embeds its data as ``const D={...}``; these tests parse that block and
check the categories against Rama's validated flag table, so a re-export of the
dashboard cannot silently merge positive, negative and scene-artefact flags again.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "index.html"
VALIDATED = ROOT / "validation" / "results" / "validated_anomalies_615.csv"

pytestmark = pytest.mark.skipif(not HTML.exists(), reason="docs/index.html not present")


@pytest.fixture(scope="module")
def page() -> tuple[str, dict]:
    html = HTML.read_text(encoding="utf-8")
    match = re.search(r"const D=(\{.*?\});\nconst M=", html, re.S)
    assert match, "embedded dashboard data block not found"
    return html, json.loads(match.group(1))


def test_review_candidates_split_into_14_positive_and_9_negative(page) -> None:
    _, D = page
    counts = Counter(r[5] for r in D["rows"])
    assert counts[0] == 579 and counts[4] == 13
    review = [r for r in D["rows"] if 1 <= r[5] <= 3]
    assert len(review) == 23
    assert sum(r[4] > 0 for r in review) == 14   # NDVI above expected
    assert sum(r[4] < 0 for r in review) == 9    # NDVI below expected


def test_scene_artefacts_are_their_own_category_on_17_may_only(page) -> None:
    _, D = page
    art = [r for r in D["rows"] if r[5] == 4]
    assert len(art) == 13
    assert {D["dates"][r[1]] for r in art} == {"2025-05-17"}
    assert all(r[4] < 0 for r in art)  # region-wide dip, never counted among the 23


def test_dashboard_matches_validated_results_table(page) -> None:
    if not VALIDATED.exists():
        pytest.skip("validation results not present")
    _, D = page
    va = pd.read_csv(VALIDATED)
    flagged = va[va["flag_category"] != "no_flag"]
    assert len(flagged) == 36
    review = flagged[flagged["flag_category"] != "scene_artifact_suspect"]
    assert (review["residual"] > 0).sum() == 14 and (review["residual"] < 0).sum() == 9
    dash = {(r[0], D["dates"][r[1]]): r[5] for r in D["rows"] if r[5] > 0}
    assert len(dash) == 36
    for row in flagged.itertuples():
        assert (row.field_id, row.date) in dash


def test_forecast_detector_flags_are_a_separate_layer(page) -> None:
    _, D = page
    rand = D["rand"]
    assert len(rand) == 15
    suspects = [x for x in rand if x[4] == 1]
    assert len(suspects) == 5 and {D["dates"][x[1]] for x in suspects} == {"2025-05-17"}
    assert len(rand) - len(suspects) == 10
    assert all(x[3] < 0 for x in rand)  # lower-tail-only detector


def test_visible_text_states_the_separated_counts_and_no_causal_claims(page) -> None:
    html, _ = page
    assert "14 positive" in html and "9 negative" in html
    assert "13 suspected scene artefacts" in html
    assert "not evidence of dust or drought as the cause" in html
    assert 'id="dirSel"' in html and 'id="detectors"' in html
    assert "flags worth inspecting in the field" not in html  # old grouped wording removed
