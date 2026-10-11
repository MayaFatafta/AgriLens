"""Regression tests for the AgriLens NDVI anomaly module.

The fixture uses synthetic data only. It verifies implementation and data-flow
invariants; it does not validate agronomic or dust/drought detection accuracy.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.ndvi_anomaly_detection import run_analysis


def make_synthetic_dataset(
    path: Path,
    *,
    include_split: bool = True,
    duplicate: bool = False,
    wrong_split_layout: bool = False,
    alter_test_field_at_index: tuple[int, float] | None = None,
) -> Path:
    """Create 20 fields with the required 9/6/5 spatial split layout."""
    rows: list[dict[str, object]] = []
    dates = pd.date_range("2025-03-01", periods=12, freq="14D")
    for i in range(20):
        field_id = f"F{i + 1:02d}"
        if wrong_split_layout and i == 8:
            split = "validation"
        else:
            split = "train" if i < 9 else "validation" if i < 15 else "test"
        base = 0.55 + 0.002 * i
        # These are synthetic, deterministic coordinates, only for testing the
        # GeoJSON serialization and coordinate-order convention [longitude, latitude].
        latitude = 30.60 + i * 0.001
        longitude = 30.20 + i * 0.001
        for j, date in enumerate(dates):
            ndvi = base + 0.025 * np.sin(j / 2.0) + 0.001 * j
            if i == 19 and j == 10:
                ndvi -= 0.18
            if alter_test_field_at_index and i == 19 and j == alter_test_field_at_index[0]:
                ndvi += alter_test_field_at_index[1]
            row: dict[str, object] = {
                "field_id": field_id,
                "date": date.strftime("%Y-%m-%d"),
                "NDVI": float(np.clip(ndvi, -1, 1)),
                "latitude": latitude,
                "longitude": longitude,
                "NDMI": 0.12 + 0.005 * np.cos(j / 2.0),
                "modeled_dust": 0.4 + 0.01 * j,
                "modeled_soil_moisture": 0.25 - 0.003 * j,
            }
            if include_split:
                row["geographic_split"] = split
            rows.append(row)
    if duplicate:
        rows.append(rows[-1].copy())
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def args_for(input_path: Path, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        input=str(input_path),
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "output" / "ndvi_anomaly_v1"),
        field_col=None,
        date_col=None,
        ndvi_col=None,
        split_col=None,
        split_map=None,
        map_field_col=None,
        map_split_col=None,
        ndmi_col=None,
        dust_col=None,
        soil_moisture_col=None,
        latitude_col=None,
        longitude_col=None,
    )


def _run_with_copy_warnings_as_errors(args: argparse.Namespace) -> dict[str, object]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.SettingWithCopyWarning)
        return run_analysis(args)


def test_end_to_end_outputs_and_geographic_splits(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic_field_date.csv")
    result = _run_with_copy_warnings_as_errors(args_for(source, tmp_path))
    out = Path(result["output_dir"])
    expected = [
        "field_date_ndvi_anomaly_results.csv",
        "heldout_test_alerts.csv",
        "all_split_anomaly_flags.csv",
        "field_summary.csv",
        "forecast_metrics.csv",
        "data_audit.json",
        "model_run_manifest.json",
        "MODELING_REPORT.md",
        "threshold_calibration_residuals.csv",
        "agrilens_spatial_alerts.geojson",
    ]
    for name in expected:
        assert (out / name).is_file(), name

    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))
    assert audit["geographic_split_field_counts"] == {"test": 5, "train": 9, "validation": 6}
    assert audit["unique_fields"] == 20
    assert audit["source_data_modified"] is False
    assert audit["spatial_alert_export"]["status"] == "written"

    metrics = pd.read_csv(out / "forecast_metrics.csv")
    test_model_names = set(metrics.loc[metrics["split"] == "test_holdout", "model"])
    assert "Persistence" in test_model_names
    assert "Ridge(alpha=" + str(json.loads((out / "model_run_manifest.json").read_text(encoding="utf-8"))["ridge_alpha_selected_from_validation"]) + ")" in test_model_names
    assert any(name in test_model_names for name in ("Selected(persistence)", "Selected(ridge)"))
    result_df = pd.read_csv(out / "field_date_ndvi_anomaly_results.csv")
    assert set(result_df["model_split"].unique()) == {"train", "validation", "test"}
    for column in ("cause_interpretation", "inspection_recommendation", "alert_reason", "pattern_screen"):
        assert column in result_df.columns
    assert result_df["cause_interpretation"].str.contains(
        "undetermined|No statistical anomaly", case=False, regex=True
    ).all()
    flagged = result_df[result_df["anomaly_flag"].astype(bool)]
    assert (flagged["residual_observed_minus_expected"] < 0).all()
    assert (flagged["residual_observed_minus_expected"] < flagged["anomaly_threshold"]).all()

    geojson = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) > 0
    for feature in geojson["features"]:
        assert feature["geometry"]["type"] == "Point"
        longitude, latitude = feature["geometry"]["coordinates"]
        assert -180 <= longitude <= 180
        assert -90 <= latitude <= 90
        assert "residual_observed_minus_expected" in feature["properties"]
        assert feature["properties"]["cause_interpretation"].startswith("Undetermined")
        assert feature["properties"]["alert_priority"] in {"Review", "High review priority"}


def test_threshold_calibration_uses_training_only_oof_residuals(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic_field_date.csv")
    result = run_analysis(args_for(source, tmp_path))
    out = Path(result["output_dir"])
    calibration = pd.read_csv(out / "threshold_calibration_residuals.csv")
    manifest = json.loads((out / "model_run_manifest.json").read_text(encoding="utf-8"))

    assert set(calibration["geographic_split"]) == {"train"}
    assert calibration["field_id"].nunique() == 9
    assert calibration["oof_fold"].nunique() >= 2
    assert len(calibration) == manifest["anomaly_calibration"]["n_training_oof_residuals"]
    assert manifest["anomaly_calibration"]["calibration_split"] == "train"
    assert manifest["anomaly_calibration"]["calibration_predictions"] == "field-group out-of-fold"
    assert "random" not in manifest["training_oof_fold_method"].lower() or "no shuffling" in manifest["training_oof_fold_method"].lower()


def test_strict_9_6_5_geographic_layout_is_enforced(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "wrong_split.csv", wrong_split_layout=True)
    with pytest.raises(ValueError, match="exactly 9 train / 6 validation / 5 test fields"):
        run_analysis(args_for(source, tmp_path))


def test_duplicate_field_date_is_rejected(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "duplicate.csv", duplicate=True)
    with pytest.raises(ValueError, match="Duplicate field-date"):
        run_analysis(args_for(source, tmp_path))


def test_missing_existing_geographic_split_is_rejected(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "no_split.csv", include_split=False)
    with pytest.raises(ValueError, match="No geographic split column"):
        run_analysis(args_for(source, tmp_path))


def test_test_field_future_target_does_not_change_earlier_forecasts(tmp_path: Path) -> None:
    original = make_synthetic_dataset(tmp_path / "original.csv")
    altered = make_synthetic_dataset(
        tmp_path / "altered.csv", alter_test_field_at_index=(10, -0.05)
    )
    original_result = run_analysis(args_for(original, tmp_path / "run1"))
    altered_result = run_analysis(args_for(altered, tmp_path / "run2"))
    original_df = pd.read_csv(Path(original_result["output_dir"]) / "field_date_ndvi_anomaly_results.csv")
    altered_df = pd.read_csv(Path(altered_result["output_dir"]) / "field_date_ndvi_anomaly_results.csv")

    before_date = pd.Timestamp("2025-07-19")  # before the modified 11th observation
    a = original_df[(original_df["model_field_id"] == "F20") & (pd.to_datetime(original_df["model_observation_date"]) < before_date)]
    b = altered_df[(altered_df["model_field_id"] == "F20") & (pd.to_datetime(altered_df["model_observation_date"]) < before_date)]
    assert a["model_observation_date"].tolist() == b["model_observation_date"].tolist()
    np.testing.assert_allclose(a["expected_ndvi"].to_numpy(), b["expected_ndvi"].to_numpy(), rtol=0, atol=1e-12)


def test_geojson_is_valid_empty_collection_when_coordinates_absent(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "no_coords.csv")
    frame = pd.read_csv(source).drop(columns=["latitude", "longitude"])
    frame.to_csv(source, index=False)
    result = run_analysis(args_for(source, tmp_path))
    out = Path(result["output_dir"])
    geojson = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))
    assert geojson == {"type": "FeatureCollection", "features": []}
    assert audit["spatial_alert_export"]["status"] == "empty_no_coordinate_columns"


def test_conflicting_historical_split_does_not_override_audited_field_split(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "conflicting_splits.csv")
    frame = pd.read_csv(source)
    frame["historical_split_recorded"] = frame["geographic_split"].replace({"validation": "train"})
    frame["field_split"] = frame.pop("geographic_split")
    frame.to_csv(source, index=False)
    result = run_analysis(args_for(source, tmp_path))
    audit = result["audit"]
    assert audit["split_source_column"] == "field_split"
    assert audit["geographic_split_field_counts"] == {"train": 9, "validation": 6, "test": 5}


def test_retrospective_scene_quality_holds_flag_without_deleting_raw_alert(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    date_to_hold = pd.date_range("2025-03-01", periods=12, freq="14D")[10].strftime("%Y-%m-%d")
    qa = tmp_path / "date_scene_QA.csv"
    pd.DataFrame({"date": [date_to_hold], "scene_qa_note": ["HIGH regional AOT: inspect imagery first"]}).to_csv(qa, index=False)
    args = args_for(source, tmp_path)
    args.scene_qa = str(qa)
    args.coordinate_reference = None
    result = run_analysis(args)
    output = Path(result["output_dir"])
    full = pd.read_csv(output / "field_date_ndvi_anomaly_results.csv")
    held = pd.read_csv(output / "scene_qa_held_alerts.csv")
    screened = pd.read_csv(output / "quality_screened_inspection_queue.csv")
    assert len(held) > 0
    assert held["anomaly_flag"].astype(bool).all()
    assert (~held["operational_review_candidate"].astype(bool)).all()
    assert (held["scene_qa_status"] == "suspected_scene_artifact").all()
    assert len(full.loc[full.anomaly_flag.astype(bool)]) == len(held) + len(screened)
    assert result["scene_qa_audit"]["held_raw_alerts"] == len(held)


def test_audited_coordinate_join_and_spatial_alerts(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    frame = pd.read_csv(source)
    ref = frame[["field_id", "latitude", "longitude", "geographic_split"]].drop_duplicates()
    ref = ref.rename(columns={"latitude": "lat", "longitude": "lon", "geographic_split": "split"})
    ref_path = tmp_path / "field_geography.csv"
    ref.to_csv(ref_path, index=False)
    args = args_for(source, tmp_path)
    args.coordinate_reference = str(ref_path)
    result = run_analysis(args)
    output = Path(result["output_dir"])
    geo = json.loads((output / "agrilens_spatial_alerts.geojson").read_text())
    assert len(geo["features"]) > 0
    first = geo["features"][0]
    assert 30.2 <= first["geometry"]["coordinates"][0] <= 30.22
    assert 30.6 <= first["geometry"]["coordinates"][1] <= 30.62
    assert "scene_qa_status" in first["properties"]
    assert result["audit"]["audited_coordinate_reference"]["matched_fields"] == 20


def test_coordinate_reference_rejects_wrong_spatial_splits(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    frame = pd.read_csv(source)
    ref = frame[["field_id", "latitude", "longitude", "geographic_split"]].drop_duplicates()
    ref = ref.rename(columns={"latitude": "lat", "longitude": "lon", "geographic_split": "split"})
    ref.loc[ref["field_id"] == "F01", "split"] = "test"
    ref_path = tmp_path / "bad_field_geography.csv"
    ref.to_csv(ref_path, index=False)
    args = args_for(source, tmp_path)
    args.coordinate_reference = str(ref_path)
    with pytest.raises(ValueError, match="disagrees with required geographic splits"):
        run_analysis(args)


def test_alert_reason_uses_positive_magnitude_below_expected(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    result = run_analysis(args_for(source, tmp_path))
    table = pd.read_csv(Path(result["output_dir"]) / "field_date_ndvi_anomaly_results.csv")
    messages = table.loc[table["anomaly_flag"].astype(bool), "alert_reason"]
    assert len(messages) > 0
    assert messages.str.contains("below expected ").all()
    assert not messages.str.contains("is -").any()


def test_suspect_scene_labels_must_have_an_explicit_qa_note(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    qa = tmp_path / "qa.csv"
    pd.DataFrame({"date": ["2025-03-01"], "scene_qa_note": [""]}).to_csv(qa, index=False)
    args = args_for(source, tmp_path)
    args.scene_qa = str(qa)
    result = run_analysis(args)
    assert result["scene_qa_audit"]["suspect_dates"] == []
    assert result["scene_qa_audit"]["held_raw_alerts"] == 0
