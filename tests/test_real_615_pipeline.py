"""End-to-end check on the REAL 615 field-date records (skipped if the data are absent)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.ndvi_anomaly_detection import run_analysis

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "validation" / "data" / "agrilens_real_field_date_QA_gated_615.csv"
QA = ROOT / "validation" / "results" / "date_scene_QA.csv"
COORDS = ROOT / "validation" / "results" / "field_geography.csv"
DATA_SHA256 = "5919ffbdc2b33b6f3b3fd9c31f534889d80b2aa80cce4ceed1f04192a21c30c6"

pytestmark = pytest.mark.skipif(not (DATA.exists() and QA.exists() and COORDS.exists()), reason="real data not present")


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("real")
    args = argparse.Namespace(
        input=str(DATA), repo_root=str(tmp), output_dir=str(tmp / "out"), field_col=None, date_col=None, ndvi_col=None,
        split_col=None, split_map=None, map_field_col=None, map_split_col=None, ndmi_col=None, dust_col=None,
        soil_moisture_col=None, latitude_col=None, longitude_col=None, scene_qa=str(QA), field_coords=str(COORDS),
    )
    return Path(run_analysis(args)["output_dir"])


def test_source_file_is_the_audited_615_table() -> None:
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == DATA_SHA256


def test_audited_split_and_counts(out: Path) -> None:
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))
    assert audit["split_source_column"] == "field_split"
    assert audit["geographic_split_field_counts"] == {"test": 5, "train": 9, "validation": 6}
    assert (audit["rows_in_input"], audit["unique_fields"], audit["unique_parseable_dates"]) == (615, 20, 33)
    assert audit["source_data_modified"] is False


def test_raw_and_quality_screened_flags(out: Path) -> None:
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))["scene_quality_screen"]
    assert (audit["raw_flags"], audit["quality_screened_flags"], audit["suspected_scene_artefact_flags"]) == (15, 10, 5)
    sus = pd.read_csv(out / "scene_artifact_suspects.csv")
    assert set(sus["model_observation_date"].str[:10]) == {"2025-05-17"} and len(sus) == 5


def test_geojson_has_verified_wgs84_points_for_all_raw_flags(out: Path) -> None:
    geo = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    assert len(geo["features"]) == 15
    for feat in geo["features"]:
        lon, lat = feat["geometry"]["coordinates"]
        assert 30.2 < lon < 30.3 and 30.6 < lat < 30.7  # Nile Delta study area, [longitude, latitude]
