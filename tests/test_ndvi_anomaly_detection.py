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
    historical_conflict: bool = False,
    second_split_column: str | None = None,
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
            if historical_conflict:
                # Mirrors the real 615-row table: a non-audited column listed FIRST, with 13 train / 7 test and no validation.
                row = {"historical_split_recorded": "train" if i < 13 else "test", **row}
            if include_split:
                row["field_split" if historical_conflict else "geographic_split"] = split
            if second_split_column:
                row[second_split_column] = "train" if i < 13 else "test"
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
        scene_qa=None,
        field_coords=None,
    )


def _run_with_copy_warnings_as_errors(args: argparse.Namespace) -> dict[str, object]:
    # pandas >= 3 uses Copy-on-Write and no longer defines SettingWithCopyWarning (chained assignment cannot occur).
    warning_cls = getattr(pd.errors, "SettingWithCopyWarning", None)
    with warnings.catch_warnings():
        if warning_cls is not None:
            warnings.simplefilter("error", warning_cls)
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
        assert feature["properties"]["alert_priority"] in {"Review", "High review priority", "Image review (suspected scene artefact)"}


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


# ---------------------------------------------------------------- correction regression tests
DIP_DATE = "2025-07-19"  # synthetic dip in field F20 (12 dates, every 14 days from 2025-03-01; index 10)


def write_scene_qa(path: Path, suspect_date: str | None = DIP_DATE) -> Path:
    dates = pd.date_range("2025-03-01", periods=12, freq="14D").strftime("%Y-%m-%d")
    note = ["HIGH regional AOT: treat dips as suspected scene/atmospheric artefact until imagery is checked"
            if d == suspect_date else "" for d in dates]
    pd.DataFrame({"date": dates, "mean_aot_s2": 0.2, "scene_qa_note": note}).to_csv(path, index=False)
    return path


def write_coords(path: Path, rows: list[tuple[str, float, float]]) -> Path:
    pd.DataFrame(rows, columns=["field_id", "lon", "lat"]).to_csv(path, index=False)
    return path


def test_audited_field_split_has_priority_over_historical_column(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "conflict.csv", historical_conflict=True)
    first_col = pd.read_csv(source, nrows=1).columns[0]
    assert first_col == "historical_split_recorded"  # the old bug picked the first split-like column
    out = Path(run_analysis(args_for(source, tmp_path))["output_dir"])
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))
    assert audit["split_source_column"] == "field_split"
    assert audit["geographic_split_field_counts"] == {"test": 5, "train": 9, "validation": 6}
    assert audit["split_selection"]["ignored_columns"]["historical_split_recorded"]["rows_disagreeing_with_selected"] > 0


def test_ambiguous_split_columns_fail_with_clear_error(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "ambiguous.csv", second_split_column="recorded_split")
    with pytest.raises(ValueError, match="Ambiguous geographic split"):
        run_analysis(args_for(source, tmp_path))


def test_explicit_historical_column_cannot_pass_the_9_6_5_check(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "conflict.csv", historical_conflict=True)
    args = args_for(source, tmp_path)
    args.split_col = "historical_split_recorded"
    with pytest.raises(ValueError, match="Required geographic splits missing|exactly 9 train / 6 validation / 5 test"):
        run_analysis(args)


def test_invalid_audited_split_labels_do_not_fall_back_to_other_column(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "bad_label.csv", historical_conflict=True)
    frame = pd.read_csv(source)
    frame.loc[0, "field_split"] = "unknown_group"
    frame.to_csv(source, index=False)
    with pytest.raises(ValueError, match="audited split column"):
        run_analysis(args_for(source, tmp_path))


def test_scene_quality_screen_keeps_raw_flags_and_separates_artefacts(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    args = args_for(source, tmp_path)
    args.scene_qa = str(write_scene_qa(tmp_path / "scene_qa.csv"))
    out = Path(run_analysis(args)["output_dir"])
    res = pd.read_csv(out / "field_date_ndvi_anomaly_results.csv")
    raw = res[res["raw_anomaly_flag"]]
    sus = res[res["scene_artifact_suspect"]]
    screened = res[res["quality_screened_flag"]]
    assert len(sus) >= 1 and set(sus["model_observation_date"].str[:10]) == {DIP_DATE}
    assert len(raw) == len(sus) + len(screened)  # nothing is dropped, only re-categorised
    assert not (sus["quality_screened_flag"]).any()
    assert (sus["review_category"] == "Suspected scene artefact - image review").all()
    assert sus["cause_interpretation"].str.startswith("Undetermined").all()
    assert sus["inspection_recommendation"].str.contains("image first", case=False).all()
    assert len(pd.read_csv(out / "all_split_anomaly_flags.csv")) == len(raw)  # raw file untouched by screening
    assert len(pd.read_csv(out / "scene_artifact_suspects.csv")) == len(sus)
    assert len(pd.read_csv(out / "quality_screened_review_queue.csv")) == len(screened)
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))["scene_quality_screen"]
    assert audit["status"] == "applied" and audit["raw_flags"] == len(raw)
    geo = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    cats = {f["properties"]["review_category"] for f in geo["features"]}
    assert "Suspected scene artefact - image review" in cats


def test_scene_qa_without_suspect_dates_changes_nothing(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    args = args_for(source, tmp_path)
    args.scene_qa = str(write_scene_qa(tmp_path / "scene_qa.csv", suspect_date=None))
    out = Path(run_analysis(args)["output_dir"])
    res = pd.read_csv(out / "field_date_ndvi_anomaly_results.csv")
    assert not res["scene_artifact_suspect"].any()
    assert res["quality_screened_flag"].sum() == res["raw_anomaly_flag"].sum() > 0


def test_geojson_uses_audited_field_coordinates_joined_by_field_id(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    pd.read_csv(source).drop(columns=["latitude", "longitude"]).to_csv(source, index=False)
    args = args_for(source, tmp_path)
    args.field_coords = str(write_coords(tmp_path / "coords.csv", [("F20", 30.2345, 30.6234), ("F01", 30.1, 30.1)]))
    out = Path(run_analysis(args)["output_dir"])
    geo = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    assert geo["features"], "F20 has a valid audited coordinate, so its alerts must be mapped"
    expected = {"F20": [30.2345, 30.6234], "F01": [30.1, 30.1]}  # [longitude, latitude]
    assert any(f["properties"]["model_field_id"] == "F20" for f in geo["features"])
    for feat in geo["features"]:
        assert feat["geometry"]["coordinates"] == expected[feat["properties"]["model_field_id"]]
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))["spatial_alert_export"]
    assert audit["field_coordinate_resolution"]["fields_with_valid_coordinates"] == 2
    assert "F02" in audit["field_coordinate_resolution"]["fields_unmapped"]


@pytest.mark.parametrize("lon,lat,reason", [
    (30.2, 95.0, "unmapped_not_valid_wgs84_range"),
    (234935.9, 3391197.4, "unmapped_not_valid_wgs84_range"),  # projected UTM metres are never guessed or transformed
    (0.0, 0.0, "unmapped_null_island_placeholder"),
    (float("nan"), float("nan"), "unmapped_missing_coordinates"),
])
def test_invalid_coordinates_stay_unmapped(tmp_path: Path, lon: float, lat: float, reason: str) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    pd.read_csv(source).drop(columns=["latitude", "longitude"]).to_csv(source, index=False)
    args = args_for(source, tmp_path)
    args.field_coords = str(write_coords(tmp_path / "coords.csv", [("F20", lon, lat)]))
    out = Path(run_analysis(args)["output_dir"])
    geo = json.loads((out / "agrilens_spatial_alerts.geojson").read_text(encoding="utf-8"))
    assert geo["features"] == []
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))["spatial_alert_export"]
    assert audit["field_coordinate_resolution"]["unmapped_reasons"]["F20"] == reason


def test_conflicting_duplicate_coordinates_stay_unmapped(tmp_path: Path) -> None:
    source = make_synthetic_dataset(tmp_path / "synthetic.csv")
    pd.read_csv(source).drop(columns=["latitude", "longitude"]).to_csv(source, index=False)
    args = args_for(source, tmp_path)
    args.field_coords = str(write_coords(tmp_path / "coords.csv", [("F20", 30.2, 30.6), ("F20", 30.3, 30.7)]))
    out = Path(run_analysis(args)["output_dir"])
    audit = json.loads((out / "data_audit.json").read_text(encoding="utf-8"))["spatial_alert_export"]
    assert audit["field_coordinate_resolution"]["unmapped_reasons"]["F20"] == "unmapped_conflicting_coordinates"
