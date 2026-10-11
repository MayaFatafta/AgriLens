#!/usr/bin/env python3
"""AgriLens NDVI forecasting + residual anomaly screening.

This module reads the project's audited field-date dataset without modifying it,
uses the existing geographic train/validation/test assignments, compares a
persistence baseline with a Ridge forecaster, calibrates a conservative lower-tail
residual threshold from training-only out-of-fold predictions, and writes a
reproducible set of outputs for the AgriLens proof of concept.

It detects statistically unusual vegetation changes. It does NOT diagnose dust,
drought, crop damage, or irrigation need.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SCRIPT_VERSION = "1.2.0"
EXPECTED_FIELD_DATE_ROWS = 615
EXPECTED_AUDITED_FIELDS = 20
EXPECTED_OBSERVATION_DATES = 33
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)

ALIASES: dict[str, list[str]] = {
    "field": [
        "field_id", "fieldid", "field_uid", "field_code", "field_name",
        "master_field_id", "agri_field_id", "plot_id", "parcel_id", "site_id",
        "field", "field_identifier", "uid",
    ],
    "date": [
        "date", "field_date", "observation_date", "obs_date", "acquisition_date",
        "sensing_date", "date_utc", "datetime", "timestamp", "system_time_start",
        "image_date", "scene_date",
    ],
    "ndvi": [
        "ndvi", "ndvi_mean", "mean_ndvi", "ndvi_median", "median_ndvi",
        "ndvi_value", "ndvi_mean_s2", "s2_ndvi", "ndvi_sentinel2",
        "ndvi_field_mean", "ndvi_field_median",
    ],
    "split": [
        "field_split", "geographic_split", "spatial_split", "geo_split", "split", "dataset_split",
        "data_split", "set", "subset", "split_name", "group_split", "partition",
    ],
    "ndmi": ["ndmi", "ndmi_mean", "mean_ndmi", "ndmi_median", "median_ndmi", "s2_ndmi"],
    "dust": ["dust", "dust_index", "dust_aod", "aod", "aerosol_optical_thickness", "modeled_dust", "modelled_dust", "dust_flag"],
    "soil_moisture": ["soil_moisture", "soilmoisture", "sm", "modeled_soil_moisture", "modelled_soil_moisture", "soil_moisture_proxy", "soil_moisture_28_to_100cm"],
    "latitude": ["latitude", "lat", "field_latitude", "field_lat", "centroid_latitude", "centroid_lat", "center_latitude", "center_lat", "y_lat"],
    "longitude": ["longitude", "lon", "lng", "long", "field_longitude", "field_lon", "centroid_longitude", "centroid_lon", "center_longitude", "center_lon", "x_lon"],
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _find_column(df: pd.DataFrame, role: str, explicit: str | None = None, required: bool = True) -> str | None:
    if explicit:
        if explicit not in df.columns:
            raise ValueError(f"Requested {role} column {explicit!r} not found. Available columns: {list(df.columns)}")
        return explicit
    normalized = {_norm(c): c for c in df.columns}
    for candidate in ALIASES.get(role, []):
        if candidate in normalized:
            return normalized[candidate]
    # Conservative fallbacks for common exports whose suffix/prefix differs.
    if role == "ndvi":
        candidates = [c for c in df.columns if "ndvi" in _norm(c) and not any(x in _norm(c) for x in ("delta", "change", "anomal", "lag", "zscore", "std", "qa", "threshold"))]
        if candidates:
            rank = lambda c: (0 if "median" in _norm(c) else 1 if "mean" in _norm(c) else 2 if _norm(c) == "ndvi" else 3, len(str(c)))
            return sorted(candidates, key=rank)[0]
    elif role == "date":
        candidates = [c for c in df.columns if any(x in _norm(c) for x in ("date", "datetime", "timestamp"))]
        if candidates:
            return candidates[0]
    elif role == "field":
        candidates = [c for c in df.columns if "field" in _norm(c) or "plot_id" in _norm(c) or "parcel_id" in _norm(c)]
        if candidates:
            return candidates[0]
    elif role == "split":
        candidates = [c for c in df.columns if ("split" in _norm(c) or "partition" in _norm(c)) and not any(x in _norm(c) for x in ("historical", "recorded", "mismatch"))]
        if candidates:
            return candidates[0]
    elif role == "latitude":
        candidates = [c for c in df.columns if _norm(c) in {"lat", "latitude", "field_lat", "field_latitude", "centroid_lat", "centroid_latitude", "center_lat", "center_latitude"}]
        if candidates:
            return candidates[0]
    elif role == "longitude":
        candidates = [c for c in df.columns if _norm(c) in {"lon", "lng", "long", "longitude", "field_lon", "field_longitude", "centroid_lon", "centroid_longitude", "center_lon", "center_longitude"}]
        if candidates:
            return candidates[0]
    if required:
        raise ValueError(f"Could not identify the {role} column. Available columns: {list(df.columns)}. Pass --{role}-col explicitly.")
    return None


def _read_table(path: Path, nrows: int | None = None) -> pd.DataFrame:
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".parquet") or suffixes.endswith(".pq"):
        return pd.read_parquet(path)
    if suffixes.endswith(".csv.gz") or suffixes.endswith(".csv") or path.suffix.lower() == ".tsv":
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        return pd.read_csv(path, nrows=nrows, sep=sep, low_memory=False)
    raise ValueError(f"Unsupported file type: {path}. Use CSV, CSV.GZ, TSV, or Parquet.")


def _is_table_path(path: Path) -> bool:
    n = path.name.lower()
    return n.endswith((".csv", ".csv.gz", ".parquet", ".pq", ".tsv"))


def _skip_candidate(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    stem = path.name.lower()
    bad_parts = {".git", ".venv", ".venv_clean", "__pycache__", "node_modules", ".pytest_cache"}
    if any(p in bad_parts or p.startswith(".venv") for p in parts):
        return True
    # The team explicitly retained the manual audited dataset as source of truth;
    # do not auto-select the optional v2/enhancement merge or its derivatives.
    if any("agrilens_v2_safe_additive_enhancement" in p for p in parts):
        return True
    if any(token in stem for token in ("enhancement", "safe_additive", "merged_v2", "backup", "manifest", "spectral", "reflectance", "wavelength", "emit_", "emit.", "emit-")):
        return True
    if any(token in stem for token in ("pixel_date", "pixel-date", "pixel_level", "pixel-level")):
        return True
    return False


def discover_dataset(repo_root: Path) -> Path:
    """Find one plausible audited field-date table; fail closed if ambiguous."""
    candidates: list[tuple[int, Path, int]] = []
    search_roots = [
        repo_root / "AgriLens_Full_Team_Dataset_2026_10_10",
        repo_root / "output" / "AgriLens_Egypt_Manual_Release_v1",
        repo_root / "output",
        repo_root / "outputs",
        repo_root / "data",
        repo_root / "inputs",
    ]
    files: set[Path] = set()
    for root in search_roots:
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and _is_table_path(path) and not _skip_candidate(path):
                    try:
                        if path.stat().st_size <= 100_000_000:
                            files.add(path)
                    except OSError:
                        continue
    # If the project folders were renamed, check the repository root as a fallback.
    if not files:
        for path in repo_root.glob("*"):
            if path.is_file() and _is_table_path(path) and not _skip_candidate(path):
                files.add(path)
    for path in files:
        stem = path.name.lower()
        if not any(token in stem for token in ("field", "screen", "observation", "dataset", "ndvi", "record", "agri", "sentinel")):
            continue
        try:
            preview = _read_table(path, nrows=5)
            fcol = _find_column(preview, "field", required=False)
            dcol = _find_column(preview, "date", required=False)
            ncol = _find_column(preview, "ndvi", required=False)
            if not (fcol and dcol and ncol):
                continue
            # Data tables this task is designed for are small field-date tables.
            sample = _read_table(path, nrows=EXPECTED_FIELD_DATE_ROWS + 1)
            rows = len(sample)
            # Reject files that clearly exceed field-date table size.
            if rows > 10_000:
                continue
            score = 0
            relative = str(path.relative_to(repo_root)).lower() if path.is_relative_to(repo_root) else str(path).lower()
            if "agrilens_egypt_manual_release_v1" in relative:
                score += 30
            if "field_date" in stem or "field-date" in stem:
                score += 15
            if "screen" in stem:
                score += 12
            if "manual" in stem or "audited" in stem:
                score += 8
            if "agrilens_full_team_dataset_2026_10_10" in relative:
                score += 6
            if rows == EXPECTED_FIELD_DATE_ROWS:
                score += 10
            if "v2" in relative or "enhancement" in relative or "merge" in stem:
                score -= 80
            candidates.append((score, path, rows))
        except Exception:
            continue
    if not candidates:
        raise FileNotFoundError(
            "Could not auto-detect the official field-date dataset. Run from the AgriLens repository root and pass "
            "--input path/to/the_audited_615_row_csv.csv. The optional v2/additive-enhancement package is deliberately excluded."
        )
    candidates.sort(key=lambda item: (item[0], item[2] == EXPECTED_FIELD_DATE_ROWS), reverse=True)
    best_score = candidates[0][0]
    tied = [c for c in candidates if c[0] == best_score]
    if len(tied) > 1:
        listing = "\n".join(f"  - {p} (preview rows={rows}, score={score})" for score, p, rows in tied[:10])
        raise RuntimeError(
            "More than one plausible audited field-date dataset was found; refusing to guess. Pass --input explicitly.\n" + listing
        )
    chosen = candidates[0][1]
    print(f"[input discovery] Selected {chosen} (candidate score {candidates[0][0]}). Verify this is the official audited source.")
    return chosen


def _parse_dates(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        nums = pd.to_numeric(series, errors="coerce")
        median = nums.dropna().median() if nums.notna().any() else np.nan
        if pd.notna(median) and 19_000_101 <= median <= 29_991_231:
            return pd.to_datetime(nums.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
        if pd.notna(median) and median > 1e12:
            return pd.to_datetime(nums, unit="ms", errors="coerce", utc=True).dt.tz_convert(None)
        if pd.notna(median) and median > 1e9:
            return pd.to_datetime(nums, unit="s", errors="coerce", utc=True).dt.tz_convert(None)
    # UTC normalization makes timezone-bearing and naive ISO dates comparable.
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)


def _normalize_split(value: Any) -> str | None:
    if pd.isna(value):
        return None
    s = _norm(value)
    if s in {"train", "training", "tr", "train_set", "training_set", "fit"} or s.startswith("train_"):
        return "train"
    if s in {"val", "valid", "validation", "validation_set", "valid_set", "dev"} or s.startswith("val_") or s.startswith("valid_"):
        return "validation"
    if s in {"test", "testing", "test_set", "testing_set", "holdout", "heldout", "hold_out"} or s.startswith("test_"):
        return "test"
    # In a few exports values may read "Training (9 fields)" etc.
    if re.search(r"(^|_)train(ing)?($|_)", s):
        return "train"
    if re.search(r"(^|_)valid(ation)?($|_)", s):
        return "validation"
    if re.search(r"(^|_)test(ing)?($|_)", s):
        return "test"
    return None


def _find_split_map(repo_root: Path, input_path: Path) -> Path | None:
    matches = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or not _is_table_path(path) or _skip_candidate(path):
            continue
        if path.resolve() == input_path.resolve():
            continue
        stem = path.name.lower()
        if not any(t in stem for t in ("split", "partition", "field_groups", "field_group")):
            continue
        try:
            preview = _read_table(path, nrows=100)
            _find_column(preview, "field", required=True)
            _find_column(preview, "split", required=True)
            matches.append(path)
        except Exception:
            continue
    return matches[0] if len(matches) == 1 else None


def _load_split_map(path: Path, field_col: str | None = None, split_col: str | None = None) -> pd.DataFrame:
    mapping = _read_table(path)
    fid = _find_column(mapping, "field", explicit=field_col)
    sc = _find_column(mapping, "split", explicit=split_col)
    out = mapping[[fid, sc]].copy()
    out.columns = ["__field", "__split_raw"]
    out["__field"] = out["__field"].astype(str).str.strip()
    out["__split"] = out["__split_raw"].map(_normalize_split)
    if out["__split"].isna().any():
        bad = sorted(out.loc[out["__split"].isna(), "__split_raw"].astype(str).unique())
        raise ValueError(f"Unrecognized split labels in {path}: {bad}")
    if out["__field"].duplicated().any():
        raise ValueError(f"Split map {path} must have exactly one row per field.")
    return out[["__field", "__split"]]


def _metric_row(y_true: np.ndarray, y_pred: np.ndarray, split: str, model_name: str, fields: Iterable[Any]) -> dict[str, Any]:
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    yt, yp = y_true[valid], y_pred[valid]
    if len(yt) == 0:
        return {"split": split, "model": model_name, "n_pairs": 0, "n_fields": 0, "mae": None, "rmse": None, "bias_observed_minus_predicted": None}
    return {
        "split": split,
        "model": model_name,
        "n_pairs": int(len(yt)),
        "n_fields": int(pd.Series(list(fields))[valid].nunique()),
        "mae": float(mean_absolute_error(yt, yp)),
        "rmse": float(math.sqrt(mean_squared_error(yt, yp))),
        "bias_observed_minus_predicted": float(np.mean(yt - yp)),
    }


def _make_pipeline(alpha: float) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=float(alpha))),
    ])


def _group_oof_predictions(
    train: pd.DataFrame,
    feature_cols: list[str],
    model_name: str,
    alpha: float,
) -> tuple[pd.Series, pd.Series]:
    """Return deterministic field-group OOF forecasts and fold IDs.

    No randomized split is used. Entire training fields are held out per fold.
    Persistence has no fitted parameters, but it is assigned through the same
    held-out-field folds so every calibration residual has an auditable OOF fold.
    """
    groups = train["__field"].astype(str)
    n_groups = int(groups.nunique())
    if n_groups < 2:
        raise ValueError("At least two training fields are required for field-group OOF predictions.")

    splitter = GroupKFold(n_splits=min(5, n_groups))
    X = train[feature_cols]
    y = train["__target"].to_numpy(dtype=float)
    predictions = pd.Series(np.nan, index=train.index, dtype=float)
    fold_ids = pd.Series(pd.NA, index=train.index, dtype="Int64")

    for fold_id, (fit_positions, heldout_positions) in enumerate(splitter.split(X, y, groups)):
        heldout_index = X.index[heldout_positions]
        if model_name == "persistence":
            # A persistence forecast is the preceding valid observation. It has
            # no trained parameters and only uses a causal lag from that field.
            fold_predictions = train.iloc[heldout_positions]["__lag1"].to_numpy(dtype=float)
        elif model_name == "ridge":
            fold_model = _make_pipeline(alpha)
            fold_model.fit(X.iloc[fit_positions], y[fit_positions])
            fold_predictions = fold_model.predict(X.iloc[heldout_positions])
        else:
            raise ValueError(f"Unknown OOF model: {model_name!r}")
        predictions.loc[heldout_index] = fold_predictions
        fold_ids.loc[heldout_index] = int(fold_id)

    if predictions.isna().any() or fold_ids.isna().any():
        raise RuntimeError("OOF prediction failed to assign every training row to exactly one field-held-out fold.")
    return predictions, fold_ids.astype(int)


def _predict_ridge_oof(train: pd.DataFrame, feature_cols: list[str], alpha: float) -> pd.Series:
    """Backward-compatible Ridge OOF helper (deterministic grouped folds)."""
    predictions, _ = _group_oof_predictions(train, feature_cols, "ridge", alpha)
    return predictions


def _robust_threshold(residuals: Iterable[float]) -> dict[str, float | int | str]:
    arr = np.asarray(list(residuals), dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 5:
        raise ValueError(f"Only {len(arr)} training residuals available; need at least 5 to calibrate a transparent anomaly threshold.")
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    sigma = float(1.4826 * mad)
    q05 = float(np.quantile(arr, 0.05))
    if sigma > 1e-8:
        raw_threshold = min(q05, med - 2.5 * sigma)
        method = "minimum of training OOF residual 5th percentile and median - 2.5 robust sigmas"
    else:
        raw_threshold = q05
        method = "training OOF residual 5th percentile because MAD is approximately zero"
        sigma = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0

    # Scientific guardrail: this module only flags lower-than-expected NDVI. If
    # the fitted lower-tail cutoff is positive, cap the operational threshold at
    # zero so a positive residual (observed NDVI above expectation) cannot alert.
    threshold = min(float(raw_threshold), 0.0)
    if raw_threshold > 0.0:
        method += "; operational threshold capped at 0.0 to flag only negative residuals"
    return {
        "n_training_oof_residuals": int(len(arr)),
        "residual_median": med,
        "residual_mad": mad,
        "robust_sigma": sigma,
        "residual_q05": q05,
        "unconstrained_lower_tail_threshold": float(raw_threshold),
        "lower_anomaly_threshold": float(threshold),
        "method": method,
        "alerts_require_negative_residual": True,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _json_value(value: Any) -> Any:
    """Convert a pandas/NumPy scalar to strict JSON-safe native values."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_spatial_alerts_geojson(
    results: pd.DataFrame,
    output_path: Path,
    *,
    latitude_col: str | None,
    longitude_col: str | None,
) -> dict[str, Any]:
    """Write RFC 7946-style GeoJSON Point features for flagged rows only.

    Source coordinates are assumed to be WGS84 latitude/longitude in decimal
    degrees. The function never guesses or transforms projected coordinates. If
    either coordinate column is absent, it writes a valid empty FeatureCollection
    and records the limitation in the audit/manifest rather than fabricating points.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    geojson: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    alert_mask = results["anomaly_flag"].fillna(False).astype(bool)
    alerts = results.loc[alert_mask].copy()
    base_audit: dict[str, Any] = {
        "output_file": str(output_path),
        "coordinate_reference": "WGS84 longitude/latitude in decimal degrees (GeoJSON RFC 7946)",
        "alert_rows_available": int(len(alerts)),
        "feature_count": 0,
        "rows_omitted_missing_or_invalid_coordinates": int(len(alerts)),
        "latitude_column": latitude_col,
        "longitude_column": longitude_col,
    }

    if not latitude_col or not longitude_col or latitude_col not in results.columns or longitude_col not in results.columns:
        base_audit["status"] = "empty_no_coordinate_columns"
        output_path.write_text(json.dumps(geojson, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        return base_audit

    lat = pd.to_numeric(alerts[latitude_col], errors="coerce")
    lon = pd.to_numeric(alerts[longitude_col], errors="coerce")
    coordinate_valid = lat.notna() & lon.notna() & np.isfinite(lat) & np.isfinite(lon) & lat.between(-90.0, 90.0) & lon.between(-180.0, 180.0)
    valid_alerts = alerts.loc[coordinate_valid].copy()
    valid_lats = lat.loc[coordinate_valid].to_numpy(dtype=float)
    valid_lons = lon.loc[coordinate_valid].to_numpy(dtype=float)
    features: list[dict[str, Any]] = []
    properties_candidates = [
        "model_field_id", "model_observation_date", "model_split", "observed_ndvi", "expected_ndvi",
        "residual_observed_minus_expected", "anomaly_threshold", "residual_robust_z", "alert_priority",
        "pattern_screen", "cause_interpretation", "alert_reason", "inspection_recommendation", "confidence_note",
        "selected_model", "days_since_previous_observation", "model_method", "source_run",
        "scene_qa_status", "scene_qa_evidence", "operational_review_candidate",
    ]
    for pos, (_, row) in enumerate(valid_alerts.iterrows()):
        properties = {key: _json_value(row[key]) for key in properties_candidates if key in valid_alerts.columns}
        properties["latitude"] = float(valid_lats[pos])
        properties["longitude"] = float(valid_lons[pos])
        properties["source_coordinate_columns"] = {"latitude": latitude_col, "longitude": longitude_col}
        field_id = str(row.get("model_field_id", "unknown-field"))
        obs_date = _json_value(row.get("model_observation_date"))
        feature: dict[str, Any] = {
            "type": "Feature",
            "id": f"{field_id}::{obs_date}",
            "geometry": {"type": "Point", "coordinates": [float(valid_lons[pos]), float(valid_lats[pos])]},
            "properties": properties,
        }
        features.append(feature)

    geojson["features"] = features
    output_path.write_text(json.dumps(geojson, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    base_audit["status"] = "written" if features else "empty_no_alerts_with_valid_coordinates"
    base_audit["feature_count"] = int(len(features))
    base_audit["rows_omitted_missing_or_invalid_coordinates"] = int(len(alerts) - len(features))
    return base_audit


def _apply_scene_qa(scored: pd.DataFrame, scene_qa_path: str | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Label flags associated with independently audited *suspected* scene effects.

    This is a retrospective quality-review overlay, not an operational causal
    detection rule. Original statistical flags remain unchanged.
    """
    out = scored.copy()
    out["model_method"] = "one_step_ndvi_forecast_lower_tail_residual"
    out["source_run"] = f"rand_model_v{SCRIPT_VERSION}"
    out["scene_qa_status"] = "not_supplied" if not scene_qa_path else "not_flagged_by_scene_qa"
    out["scene_qa_evidence"] = ""
    flagged = out["anomaly_flag"].fillna(False).astype(bool)
    audit = {"scene_qa_source": None, "suspect_dates": [], "held_raw_alerts": 0, "retrospective_overlay": bool(scene_qa_path)}
    if scene_qa_path:
        path = Path(scene_qa_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Scene QA reference missing: {path}")
        qa = pd.read_csv(path)
        if not {"date", "scene_qa_note"}.issubset(qa.columns):
            raise ValueError("Scene QA CSV must include date and scene_qa_note columns.")
        qa["__day"] = _parse_dates(qa["date"]).dt.strftime("%Y-%m-%d")
        if qa["__day"].isna().any() or qa["__day"].duplicated().any():
            raise ValueError("Scene QA reference must contain unique, valid dates.")
        suspicious = qa[qa["scene_qa_note"].notna() & qa["scene_qa_note"].astype(str).str.strip().ne("")]
        suspect_days = set(suspicious["__day"].tolist())
        audit["scene_qa_source"] = str(path)
        audit["scene_qa_sha256"] = _sha256(path)
        audit["suspect_dates"] = sorted(suspect_days)
        notes = dict(zip(suspicious["__day"], suspicious["scene_qa_note"].astype(str)))
        day = out["__date"].dt.strftime("%Y-%m-%d")
        scene_mask = day.isin(suspect_days)
        out.loc[scene_mask, "scene_qa_status"] = "suspected_scene_artifact"
        out.loc[scene_mask, "scene_qa_evidence"] = day.loc[scene_mask].map(notes).fillna("")
        suspect_flags = flagged & scene_mask
        audit["held_raw_alerts"] = int(suspect_flags.sum())
        out.loc[suspect_flags, "alert_priority"] = "Scene QA hold"
        out.loc[suspect_flags, "inspection_recommendation"] = (
            "Suspected atmospheric/image-quality scene effect: inspect imagery and source QA first; "
            "do not treat this satellite observation alone as evidence requiring a crop-field visit."
        )
    out["operational_review_candidate"] = flagged & out["scene_qa_status"].ne("suspected_scene_artifact")
    audit["raw_statistical_flags"] = int(flagged.sum())
    audit["quality_screened_review_candidates"] = int(out["operational_review_candidate"].sum())
    return out, audit


def _attach_audited_coordinates(
    results: pd.DataFrame, reference: str | None
) -> tuple[pd.DataFrame, str | None, str | None, dict[str, Any]]:
    """Join explicitly supplied audited WGS84 field centroids, failing closed."""
    if not reference:
        return results, None, None, {"status": "not_supplied"}
    path = Path(reference).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audited field geography CSV missing: {path}")
    df = pd.read_csv(path)
    mandatory = {"field_id", "lat", "lon", "split"}
    if not mandatory.issubset(df.columns):
        raise ValueError(f"Audited geography CSV must include {sorted(mandatory)} (WGS84 decimal degrees).")
    df["__field_key"] = df["field_id"].astype(str).str.strip()
    if df["__field_key"].duplicated().any() or df["__field_key"].isna().any():
        raise ValueError("Audited geography must contain exactly one coordinate pair per field.")
    for c,lo,hi in (("lon",-180,180),("lat",-90,90)):
        values = pd.to_numeric(df[c], errors="coerce")
        if not (values.notna() & np.isfinite(values) & values.between(lo,hi)).all():
            raise ValueError(f"Invalid {c} in audited WGS84 geography; no coordinates fabricated.")
        df[c] = values
    df["__geo_split"] = df["split"].map(_normalize_split)
    if df["__geo_split"].isna().any():
        raise ValueError("Unknown geographic split in audited geography CSV.")
    unique_results = results[["model_field_id", "model_split"]].drop_duplicates()
    unique_results["__field_key"] = unique_results["model_field_id"].astype(str).str.strip()
    matches = unique_results.merge(df[["__field_key", "__geo_split"]], on="__field_key",how="left",validate="one_to_one")
    if matches["__geo_split"].isna().any() or (matches["model_split"] != matches["__geo_split"]).any():
        raise ValueError("Audited field geography missing fields or disagrees with required geographic splits.")
    if len(matches) != len(df):
        raise ValueError("Audited coordinate reference field count does not match model field count.")
    geo = df.set_index("__field_key")
    joined = results.copy()
    keys = joined["model_field_id"].astype(str).str.strip()
    joined["field_latitude_wgs84"] = keys.map(geo["lat"]).astype(float)
    joined["field_longitude_wgs84"] = keys.map(geo["lon"]).astype(float)
    return joined, "field_latitude_wgs84", "field_longitude_wgs84", {
        "status": "joined_audited_wgs84_field_centroids", "source_file": str(path),
        "source_sha256": _sha256(path), "matched_fields": int(len(matches)),
        "crs_assumption": "Audited field_geography.csv uses WGS84 lat/lon in decimal degrees; inspect upstream provenance if uncertain.",
    }


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if args.input == "auto":
        input_path = discover_dataset(repo_root)
    else:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input dataset does not exist: {input_path}")
    df_raw = _read_table(input_path).copy()
    if df_raw.empty:
        raise ValueError(f"Dataset is empty: {input_path}")

    field_col = _find_column(df_raw, "field", args.field_col)
    date_col = _find_column(df_raw, "date", args.date_col)
    ndvi_col = _find_column(df_raw, "ndvi", args.ndvi_col)
    split_col = _find_column(df_raw, "split", args.split_col, required=False)

    df = df_raw.copy().reset_index(drop=True)
    df["__source_row"] = np.arange(len(df), dtype=int)
    raw_field_ids = df[field_col].astype("string").str.strip()
    invalid_field_id = raw_field_ids.isna() | raw_field_ids.eq("")
    if invalid_field_id.any():
        bad_rows = np.flatnonzero(invalid_field_id.to_numpy())[:10].tolist()
        raise ValueError(f"Missing/empty field IDs detected in source rows {bad_rows}. Fix the source explicitly before modeling.")
    df["__field"] = raw_field_ids.astype(str)
    df["__date"] = _parse_dates(df[date_col])
    df["__target"] = pd.to_numeric(df[ndvi_col], errors="coerce")
    invalid_ndvi = df["__target"].notna() & ~df["__target"].between(-1.0, 1.0)
    invalid_ndvi_count = int(invalid_ndvi.sum())
    df.loc[invalid_ndvi, "__target"] = np.nan
    bad_date_count = int(df["__date"].isna().sum())
    if bad_date_count:
        warnings.warn(f"{bad_date_count} rows have unparseable dates and will be excluded from temporal pairs.")
        df = df[df["__date"].notna()].copy()
    if df["__field"].isna().any() or (df["__field"].str.len() == 0).any():
        raise ValueError("Missing/empty field IDs detected. Fix or remove them before modeling.")
    if df.duplicated(["__field", "__date"]).any():
        sample = df.loc[df.duplicated(["__field", "__date"], keep=False), [field_col, date_col]].head(10)
        raise ValueError("Duplicate field-date rows detected. Resolve duplicates explicitly rather than silently aggregating.\n" + sample.to_string(index=False))

    if split_col:
        df["__split"] = df[split_col].map(_normalize_split)
        if df["__split"].isna().any():
            raw_bad = sorted(df.loc[df["__split"].isna(), split_col].astype(str).unique())
            if args.split_map:
                raise ValueError(f"A split column was detected but contains unrecognized labels {raw_bad}. Remove --split-col or correct labels before using --split-map.")
            raise ValueError(f"Unrecognized/missing values in split column {split_col!r}: {raw_bad}. Use --split-map or --split-col with the existing geographic split.")
    else:
        split_map_path = Path(args.split_map).expanduser().resolve() if args.split_map else _find_split_map(repo_root, input_path)
        if split_map_path is None or not split_map_path.exists():
            raise ValueError(
                "No geographic split column was found in the dataset and a unique split-map file could not be detected. "
                "Because the project requires preserving its 9/6/5 geographic field split, this script will not create a random split. "
                "Pass --split-map path/to/the_existing_field_split.csv or point --input to the table that already contains the split."
            )
        sm = _load_split_map(split_map_path, args.map_field_col, args.map_split_col)
        df = df.merge(sm, left_on="__field", right_on="__field", how="left", validate="many_to_one")
        if df["__split"].isna().any():
            missing_fields = sorted(df.loc[df["__split"].isna(), "__field"].unique())
            raise ValueError(f"Split mapping {split_map_path} does not cover these fields: {missing_fields}")
        split_col = "__split"
    field_splits = df.groupby("__field")["__split"].nunique()
    if (field_splits > 1).any():
        bad_fields = field_splits[field_splits > 1].index.tolist()
        raise ValueError(f"A field appears in more than one split; geographic isolation is broken for: {bad_fields}")
    present_splits = set(df["__split"].dropna())
    missing_splits = {"train", "validation", "test"} - present_splits
    if missing_splits:
        raise ValueError(f"Required geographic splits missing: {sorted(missing_splits)}. Found: {sorted(present_splits)}")

    # The project's audited spatial split is a fixed protocol. Do not repair,
    # randomize, rebalance, or silently reinterpret the existing assignments.
    split_field_counts = df.groupby("__split")["__field"].nunique().to_dict()
    expected_split_field_counts = {"train": 9, "validation": 6, "test": 5}
    actual_split_field_counts = {k: int(split_field_counts.get(k, 0)) for k in expected_split_field_counts}
    if actual_split_field_counts != expected_split_field_counts or df["__field"].nunique() != EXPECTED_AUDITED_FIELDS:
        raise ValueError(
            "The required geographic split is exactly 9 train / 6 validation / 5 test fields (20 unique fields). "
            f"Found fields by split: {actual_split_field_counts}; total unique fields={df['__field'].nunique()}. "
            "Use the original audited assignments; this script will not create or randomize a replacement split."
        )

    # Build causal, within-field time-series predictors: every feature is from the
    # past, or calendar information known for the target acquisition date.
    ndmi_col = _find_column(df, "ndmi", args.ndmi_col, required=False)
    dust_col = _find_column(df, "dust", args.dust_col, required=False)
    soil_col = _find_column(df, "soil_moisture", args.soil_moisture_col, required=False)
    df = df.sort_values(["__field", "__date"]).reset_index(drop=True)
    # Work from valid NDVI observations so lag steps mean previous valid acquisition.
    valid_rows = df[df["__target"].notna()].copy()
    pair_parts = []
    for field_id, g in valid_rows.groupby("__field", sort=False):
        g = g.sort_values("__date").copy()
        if len(g) < 2:
            continue
        g["__lag1"] = g["__target"].shift(1)
        g["__lag2"] = g["__target"].shift(2)
        g["__lag3"] = g["__target"].shift(3)
        g["__previous_date"] = g["__date"].shift(1)
        g["__days_since_prev"] = (g["__date"] - g["__previous_date"]).dt.total_seconds() / 86400.0
        g["__previous_delta"] = g["__lag1"] - g["__lag2"]
        g["__delta_3obs"] = g["__lag1"] - g["__lag3"]
        doy = g["__date"].dt.dayofyear.astype(float)
        g["__doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
        g["__doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
        if ndmi_col:
            g["__lag1_ndmi"] = pd.to_numeric(g[ndmi_col], errors="coerce").shift(1)
        if dust_col:
            g["__lag1_dust"] = pd.to_numeric(g[dust_col], errors="coerce").shift(1)
        if soil_col:
            g["__lag1_soil_moisture"] = pd.to_numeric(g[soil_col], errors="coerce").shift(1)
        pair_parts.append(g[g["__lag1"].notna()].copy())
    if not pair_parts:
        raise ValueError("No consecutive valid NDVI observations found. Check NDVI values and field/date columns.")
    pairs = pd.concat(pair_parts, ignore_index=True)

    base_features = ["__lag1", "__lag2", "__previous_delta", "__delta_3obs", "__days_since_prev", "__doy_sin", "__doy_cos"]
    # Establish geographic groups before deciding optional features. Availability
    # is checked against training fields only, not the held-out data.
    train = pairs[pairs["__split"] == "train"].copy()
    val = pairs[pairs["__split"] == "validation"].copy()
    test = pairs[pairs["__split"] == "test"].copy()
    optional_features = [c for c in ("__lag1_ndmi", "__lag1_dust", "__lag1_soil_moisture")
                         if c in pairs.columns and train[c].notna().any()]
    feature_cols = base_features + optional_features
    for c in feature_cols:
        pairs[c] = pd.to_numeric(pairs[c], errors="coerce")
    train = pairs[pairs["__split"] == "train"].copy()
    val = pairs[pairs["__split"] == "validation"].copy()
    test = pairs[pairs["__split"] == "test"].copy()
    if len(train) < 10 or train["__field"].nunique() < 2:
        raise ValueError(f"Insufficient training data after temporal pairing: {len(train)} pairs across {train['__field'].nunique()} fields.")
    if len(val) < 3 or len(test) < 3:
        warnings.warn(f"Few validation/test pairs: validation={len(val)}, test={len(test)}; metrics may be unstable.")

    # Select alpha only on validation. Ridge is not forced to win; persistence is
    # retained if it performs better, consistent with the prior experiment summary.
    ridge_candidates: list[dict[str, Any]] = []
    ridge_val_models: dict[float, Pipeline] = {}
    for alpha in RIDGE_ALPHAS:
        model = _make_pipeline(alpha)
        model.fit(train[feature_cols], train["__target"])
        pred_val = model.predict(val[feature_cols]) if len(val) else np.array([])
        score = float(mean_absolute_error(val["__target"], pred_val)) if len(val) else float("inf")
        ridge_candidates.append({"alpha": alpha, "validation_mae": score})
        ridge_val_models[alpha] = model
    selected_alpha = min(ridge_candidates, key=lambda d: d["validation_mae"])["alpha"]
    ridge = ridge_val_models[selected_alpha]

    # Validation-only selection of the forecast baseline. Test scores do not select it.
    persistence_val_mae = float(mean_absolute_error(val["__target"], val["__lag1"])) if len(val) else float("inf")
    ridge_val_mae = next(d["validation_mae"] for d in ridge_candidates if d["alpha"] == selected_alpha)
    if persistence_val_mae <= ridge_val_mae:
        selected_model = "persistence"
    else:
        selected_model = "ridge"

    # Calibration uses only predictions produced for training rows by a fold model
    # that held out the entire target field. No validation/test residual enters it.
    train_persistence_oof, train_fold_ids = _group_oof_predictions(train, feature_cols, "persistence", selected_alpha)
    train_ridge_oof_series, ridge_fold_ids = _group_oof_predictions(train, feature_cols, "ridge", selected_alpha)
    if not train_fold_ids.equals(ridge_fold_ids):
        raise RuntimeError("Internal error: persistence and Ridge OOF fold assignments differ.")
    train_persistence_pred = train_persistence_oof.to_numpy(dtype=float)
    train_ridge_oof_pred = train_ridge_oof_series.to_numpy(dtype=float)
    train_cal_pred = train_persistence_pred if selected_model == "persistence" else train_ridge_oof_pred
    train_cal_residuals = train["__target"].to_numpy(dtype=float) - train_cal_pred
    threshold_info = _robust_threshold(train_cal_residuals)
    threshold_info["calibration_split"] = "train"
    threshold_info["calibration_predictions"] = "field-group out-of-fold"
    threshold_info["n_training_fields"] = int(train["__field"].nunique())
    threshold_info["n_oof_folds"] = int(train_fold_ids.nunique())
    threshold = float(threshold_info["lower_anomaly_threshold"])
    residual_median = float(threshold_info["residual_median"])
    robust_sigma = float(threshold_info["robust_sigma"])

    # Score train with OOF predictions; score validation/test using train-fitted Ridge.
    scored_parts = []
    for split_name, subset in (("train", train), ("validation", val), ("test", test)):
        if subset.empty:
            continue
        out = subset.copy()
        out["pred_persistence"] = out["__lag1"].astype(float)
        if split_name == "train":
            out["pred_ridge"] = train_ridge_oof_pred
            out["training_oof_fold"] = train_fold_ids.to_numpy(dtype=int)
        else:
            out["pred_ridge"] = ridge.predict(out[feature_cols])
            out["training_oof_fold"] = np.nan
        out["selected_model"] = selected_model
        out["expected_ndvi"] = out["pred_persistence"] if selected_model == "persistence" else out["pred_ridge"]
        out["residual_observed_minus_expected"] = out["__target"] - out["expected_ndvi"]
        out["anomaly_threshold"] = threshold
        out["ndvi_change_from_previous"] = out["__target"] - out["__lag1"]
        out["residual_robust_z"] = (out["residual_observed_minus_expected"] - residual_median) / robust_sigma if robust_sigma > 1e-8 else np.nan
        out["anomaly_flag"] = out["residual_observed_minus_expected"] < threshold
        scored_parts.append(out)
    scored = pd.concat(scored_parts, ignore_index=True)

    # Consecutive negative changes are a pattern screen only, not evidence of a cause.
    scored = scored.sort_values(["__field", "__date"]).reset_index(drop=True)
    scored["negative_changes_last_3"] = scored.groupby("__field")["ndvi_change_from_previous"].transform(
        lambda s: (s < 0).rolling(3, min_periods=3).sum()
    )
    scored["pattern_screen"] = "No anomaly flag"
    flagged = scored["anomaly_flag"].fillna(False).astype(bool)
    persistent = flagged & scored["negative_changes_last_3"].ge(2).fillna(False)
    # Explicit .loc[column-mask, column] assignments avoid chained assignment and
    # remain compatible with pandas Copy-on-Write semantics.
    scored.loc[flagged & ~persistent, "pattern_screen"] = "Abrupt/isolated anomaly — review"
    scored.loc[persistent, "pattern_screen"] = "Repeated negative changes — review trend"

    scored["cause_interpretation"] = "No statistical anomaly flag; this does not prove absence of stress"
    scored.loc[flagged, "cause_interpretation"] = "Undetermined; requires independent field verification"

    scored["alert_priority"] = "No alert"
    scored.loc[flagged, "alert_priority"] = "Review"
    high_priority = flagged & pd.to_numeric(scored["residual_robust_z"], errors="coerce").le(-3.5).fillna(False)
    scored.loc[high_priority, "alert_priority"] = "High review priority"

    scored["alert_reason"] = "Residual did not cross the training-calibrated lower threshold."
    scored.loc[flagged, "alert_reason"] = scored.loc[flagged].apply(
        lambda r: (f"Observed NDVI is {abs(float(r['residual_observed_minus_expected'])):.3f} below expected "
                   f"(signed residual {_fmt(r['residual_observed_minus_expected'], 3)}; threshold {_fmt(threshold, 3)})."), axis=1
    )

    scored["inspection_recommendation"] = (
        "Continue routine monitoring; absence of an anomaly flag does not establish that the crop is healthy."
    )
    scored.loc[flagged, "inspection_recommendation"] = (
        "Review crop condition and image quality; verify irrigation records and root-zone moisture before changing water delivery."
    )

    # Long acquisition gaps are disclosed as lower-confidence context.
    training_gaps = train["__days_since_prev"].dropna().to_numpy(float)
    gap_q95 = float(np.quantile(training_gaps, 0.95)) if len(training_gaps) else None
    if gap_q95 is not None:
        scored["long_observation_gap"] = scored["__days_since_prev"] > gap_q95
        scored.loc[scored["long_observation_gap"], "confidence_note"] = "Lower confidence: observation gap exceeds training-set 95th percentile"
        scored.loc[~scored["long_observation_gap"], "confidence_note"] = "No long-gap warning from this rule"
    else:
        scored["long_observation_gap"] = False
        scored["confidence_note"] = "Gap confidence unavailable"

    scored, scene_qa_audit = _apply_scene_qa(scored, getattr(args, "scene_qa", None))

    # Preserve original source values and add outputs. No source rows are overwritten.
    source_cols = [c for c in df_raw.columns if c not in {"__source_row"}]
    source_lookup = df.set_index("__source_row", drop=False)
    scored["__source_row"] = scored["__source_row"].astype(int)
    original_for_scored = source_lookup.loc[scored["__source_row"].to_numpy(), source_cols].reset_index(drop=True)
    derived_cols = [
        "__field", "__date", "__split", "__target", "__lag1", "__lag2", "__previous_delta", "__delta_3obs",
        "__days_since_prev", "__doy_sin", "__doy_cos", *optional_features,
        "pred_persistence", "pred_ridge", "selected_model", "expected_ndvi", "residual_observed_minus_expected",
        "anomaly_threshold", "ndvi_change_from_previous", "residual_robust_z", "anomaly_flag", "negative_changes_last_3",
        "training_oof_fold",
        "pattern_screen", "cause_interpretation", "alert_priority", "alert_reason", "inspection_recommendation", "long_observation_gap", "confidence_note",
        "model_method", "source_run", "scene_qa_status", "scene_qa_evidence", "operational_review_candidate",
    ]
    keep_derived = [c for c in derived_cols if c in scored.columns]
    results = pd.concat([original_for_scored, scored[keep_derived].reset_index(drop=True)], axis=1)
    results = results.rename(columns={
        "__field": "model_field_id", "__date": "model_observation_date", "__split": "model_split",
        "__target": "observed_ndvi", "__lag1": "previous_ndvi", "__lag2": "ndvi_two_observations_back",
        "__previous_delta": "previous_ndvi_change", "__delta_3obs": "ndvi_change_across_previous_three_observations",
        "__days_since_prev": "days_since_previous_observation", "__doy_sin": "target_day_of_year_sin",
        "__doy_cos": "target_day_of_year_cos",
    })

    metric_rows = []
    for split_name, subset in (("train_oof", train), ("validation", val), ("test_holdout", test)):
        if subset.empty:
            continue
        if split_name == "train_oof":
            persistence_pred = train_persistence_pred
            ridge_pred = train_ridge_oof_pred
        else:
            persistence_pred = subset["__lag1"].to_numpy(float)
            ridge_pred = ridge.predict(subset[feature_cols])
        target = subset["__target"].to_numpy(float)
        fields = subset["__field"].to_numpy()
        metric_rows.append(_metric_row(target, persistence_pred, split_name, "Persistence", fields))
        metric_rows.append(_metric_row(target, ridge_pred, split_name, f"Ridge(alpha={selected_alpha})", fields))
        selected_pred = persistence_pred if selected_model == "persistence" else ridge_pred
        metric_rows.append(_metric_row(target, selected_pred, split_name, f"Selected({selected_model})", fields))
    metrics_df = pd.DataFrame(metric_rows)

    test_scored = scored[scored["__split"] == "test"].copy()
    test_alerts = test_scored[test_scored["anomaly_flag"].fillna(False)].copy()
    field_summary = scored.groupby(["__field", "__split"], as_index=False).agg(
        observations_scored=("__target", "size"),
        mean_observed_ndvi=("__target", "mean"),
        last_observed_ndvi=("__target", "last"),
        anomaly_flags=("anomaly_flag", "sum"),
        high_priority_flags=("alert_priority", lambda s: int((s == "High review priority").sum())),
        largest_negative_change=("ndvi_change_from_previous", "min"),
        median_abs_residual=("residual_observed_minus_expected", lambda s: float(np.median(np.abs(s.dropna()))) if s.notna().any() else np.nan),
    )

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (repo_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    results, audited_lat, audited_lon, coordinate_audit = _attach_audited_coordinates(
        results, getattr(args, "coordinate_reference", None)
    )
    results.to_csv(output_dir / "field_date_ndvi_anomaly_results.csv", index=False)
    results[results["anomaly_flag"].fillna(False)].to_csv(output_dir / "all_split_anomaly_flags.csv", index=False)
    test_alerts.to_csv(output_dir / "heldout_test_alerts.csv", index=False)
    field_summary.to_csv(output_dir / "field_summary.csv", index=False)
    metrics_df.to_csv(output_dir / "forecast_metrics.csv", index=False)

    results[results["operational_review_candidate"].astype(bool)].to_csv(
        output_dir / "quality_screened_inspection_queue.csv", index=False
    )
    results[results["anomaly_flag"].astype(bool) & (results["scene_qa_status"] == "suspected_scene_artifact")].to_csv(
        output_dir / "scene_qa_held_alerts.csv", index=False
    )

    # Export the actual residuals used for threshold calibration. This provides a
    # compact audit trail that every threshold residual came from a training-field
    # OOF prediction rather than validation/test data or in-sample fitted values.
    calibration_table = train[["__field", "__date", "__target", "__split"]].copy()
    calibration_table["oof_fold"] = train_fold_ids.to_numpy(dtype=int)
    calibration_table["expected_ndvi_oof"] = train_cal_pred
    calibration_table["residual_observed_minus_expected_oof"] = train_cal_residuals
    calibration_table = calibration_table.rename(columns={
        "__field": "field_id", "__date": "observation_date", "__target": "observed_ndvi", "__split": "geographic_split"
    })
    calibration_table.to_csv(output_dir / "threshold_calibration_residuals.csv", index=False)

    latitude_col = _find_column(df_raw, "latitude", getattr(args, "latitude_col", None), required=False)
    longitude_col = _find_column(df_raw, "longitude", getattr(args, "longitude_col", None), required=False)
    latitude_col = audited_lat or latitude_col
    longitude_col = audited_lon or longitude_col
    geojson_audit = _write_spatial_alerts_geojson(
        results,
        output_dir / "agrilens_spatial_alerts.geojson",
        latitude_col=latitude_col,
        longitude_col=longitude_col,
    )

    screened_geojson_audit = _write_spatial_alerts_geojson(
        results[results["operational_review_candidate"].astype(bool)].copy(),
        output_dir / "agrilens_screened_spatial_alerts.geojson",
        latitude_col=latitude_col, longitude_col=longitude_col,
    )

    # Data audit and reproducibility metadata.
    split_field_counts = df.groupby("__split")["__field"].nunique().to_dict()
    split_row_counts = df.groupby("__split").size().to_dict()
    audit = {
        "input_file": str(input_path),
        "input_sha256": _sha256(input_path),
        "rows_in_input": int(len(df_raw)),
        "unique_fields": int(df["__field"].nunique()),
        "unique_parseable_dates": int(df["__date"].nunique()),
        "rows_with_invalid_ndvi_outside_minus1_to_1": invalid_ndvi_count,
        "rows_with_unparseable_date_excluded": bad_date_count,
        "field_date_duplicate_check": "passed; no duplicate field-date keys",
        "geographic_split_field_counts": {str(k): int(v) for k, v in split_field_counts.items()},
        "geographic_split_row_counts": {str(k): int(v) for k, v in split_row_counts.items()},
        "expected_reference_counts": {
            "field_date_rows": EXPECTED_FIELD_DATE_ROWS,
            "audited_fields": EXPECTED_AUDITED_FIELDS,
            "observation_dates": EXPECTED_OBSERVATION_DATES,
        },
        "reference_count_checks": {
            "rows_match_615": bool(len(df_raw) == EXPECTED_FIELD_DATE_ROWS),
            "fields_match_20": bool(df["__field"].nunique() == EXPECTED_AUDITED_FIELDS),
            "dates_match_33": bool(df["__date"].nunique() == EXPECTED_OBSERVATION_DATES),
        },
        "ndvi_source_column": ndvi_col,
        "date_source_column": date_col,
        "field_source_column": field_col,
        "split_source_column": split_col,
        "optional_lagged_context_features": optional_features,
        "latitude_source_column": latitude_col,
        "longitude_source_column": longitude_col,
        "spatial_alert_export": geojson_audit,
        "quality_screened_spatial_alert_export": screened_geojson_audit,
        "audited_coordinate_reference": coordinate_audit,
        "scene_quality_overlay": scene_qa_audit,
        "modelled_field_date_rows": int(len(results)),
        "training_oof_residual_rows": int(len(calibration_table)),
        "training_oof_field_count": int(calibration_table["field_id"].nunique()),
        "source_data_modified": False,
    }
    with (output_dir / "data_audit.json").open("w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False, default=str)

    test_metrics = metrics_df[metrics_df["split"] == "test_holdout"].to_dict(orient="records")
    validation_metrics = metrics_df[metrics_df["split"] == "validation"].to_dict(orient="records")
    manifest = {
        "project": "AgriLens — Dust or Drought?",
        "task": "NDVI forecasting baseline comparison and residual anomaly screening",
        "script_version": SCRIPT_VERSION,
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path),
        "input_sha256": audit["input_sha256"],
        "output_directory": str(output_dir),
        "selected_forecaster_from_validation": selected_model,
        "ridge_alpha_selected_from_validation": float(selected_alpha),
        "ridge_alpha_candidates": ridge_candidates,
        "validation_persistence_mae": persistence_val_mae,
        "validation_selected_ridge_mae": ridge_val_mae,
        "features_used": feature_cols,
        "anomaly_calibration": threshold_info,
        "training_oof_calibration_output": str(output_dir / "threshold_calibration_residuals.csv"),
        "training_oof_fold_method": "deterministic GroupKFold over training fields only; no shuffling",
        "spatial_alerts_geojson": str(output_dir / "agrilens_spatial_alerts.geojson"),
        "quality_screened_spatial_alerts_geojson": str(output_dir / "agrilens_screened_spatial_alerts.geojson"),
        "scene_quality_overlay": scene_qa_audit,
        "audited_coordinate_reference": coordinate_audit,
        "spatial_alert_export": geojson_audit,
        "quality_screened_spatial_alert_export": screened_geojson_audit,
        "audited_coordinate_reference": coordinate_audit,
        "scene_quality_overlay": scene_qa_audit,
        "training_gap_95th_percentile_days": gap_q95,
        "test_metrics": test_metrics,
        "validation_metrics": validation_metrics,
        "interpretation_guardrail": "No damage labels; these are statistical anomaly alerts, not verified dust/drought diagnoses.",
    }
    with (output_dir / "model_run_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

    # Plotting is optional: model and CSV results remain available without matplotlib.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        train_resid = train["__target"].to_numpy(float) - train_cal_pred
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(train_resid[np.isfinite(train_resid)], bins=20)
        ax.axvline(threshold, linestyle="--", label=f"Training-only lower threshold: {threshold:.4f}")
        ax.set_title("AgriLens training OOF residual calibration")
        ax.set_xlabel("Observed NDVI − expected NDVI")
        ax.set_ylabel("Number of field-date observations")
        ax.legend()
        fig.tight_layout()
        fig.savefig(figures_dir / "training_residual_threshold.png", dpi=160)
        plt.close(fig)

        if len(test_scored):
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.scatter(test_scored["expected_ndvi"], test_scored["__target"], alpha=0.75)
            lims = [min(test_scored["expected_ndvi"].min(), test_scored["__target"].min()), max(test_scored["expected_ndvi"].max(), test_scored["__target"].max())]
            ax.plot(lims, lims, linestyle="--")
            ax.set_xlabel("Expected NDVI")
            ax.set_ylabel("Observed NDVI")
            ax.set_title(f"Held-out test observations — selected model: {selected_model}")
            fig.tight_layout()
            fig.savefig(figures_dir / "test_observed_vs_expected.png", dpi=160)
            plt.close(fig)

        # Highest-priority held-out field history, useful as a demo figure.
        if len(test_scored):
            candidate_fields = test_scored.groupby("__field")["anomaly_flag"].sum().sort_values(ascending=False)
            if len(candidate_fields):
                top_field = candidate_fields.index[0]
                hist = test_scored[test_scored["__field"] == top_field].sort_values("__date")
                fig, ax = plt.subplots(figsize=(9, 5))
                ax.plot(hist["__date"], hist["__target"], marker="o", label="Observed NDVI")
                ax.plot(hist["__date"], hist["expected_ndvi"], marker=".", linestyle="--", label="Expected NDVI")
                a = hist[hist["anomaly_flag"].fillna(False)]
                if len(a):
                    ax.scatter(a["__date"], a["__target"], marker="x", s=80, label="Anomaly flag")
                ax.set_title(f"Held-out field review example: {top_field}")
                ax.set_ylabel("NDVI")
                ax.set_xlabel("Observation date")
                ax.legend()
                fig.autofmt_xdate()
                fig.tight_layout()
                fig.savefig(figures_dir / "heldout_field_review_example.png", dpi=160)
                plt.close(fig)
    except Exception as exc:  # plotting must not invalidate the core CSV outputs
        warnings.warn(f"Optional figure generation failed: {exc}")

    report = _build_report(audit, manifest, metrics_df, scored, threshold_info, output_dir)
    (output_dir / "MODELING_REPORT.md").write_text(report, encoding="utf-8")
    return {"input_path": str(input_path), "output_dir": str(output_dir), "audit": audit, "manifest": manifest, "metrics": metrics_df.to_dict(orient="records"), "alert_count_test": int(len(test_alerts)), "scene_qa_audit": scene_qa_audit}


def _fmt(v: Any, n: int = 5) -> str:
    try:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "N/A"
        return f"{float(v):.{n}f}"
    except (TypeError, ValueError):
        return str(v)


def _build_report(audit: dict[str, Any], manifest: dict[str, Any], metrics_df: pd.DataFrame, scored: pd.DataFrame, threshold_info: dict[str, Any], output_dir: Path) -> str:
    def metric(split: str, name: str, col: str) -> Any:
        sel = metrics_df[(metrics_df["split"] == split) & (metrics_df["model"] == name)]
        return sel.iloc[0][col] if len(sel) else None
    alpha = manifest["ridge_alpha_selected_from_validation"]
    ridge_name = f"Ridge(alpha={alpha})"
    selected_name = f"Selected({manifest['selected_forecaster_from_validation']})"
    test_rows = metrics_df[metrics_df["split"] == "test_holdout"]
    test_counts = {r["model"]: r["n_pairs"] for _, r in test_rows.iterrows()}
    alerts = scored[(scored["__split"] == "test") & scored["anomaly_flag"].fillna(False)]
    fields_flagged = sorted(alerts["__field"].astype(str).unique().tolist())
    qa_overlay = audit["scene_quality_overlay"]
    qa_note = (f"Retrospective scene QA source: `{qa_overlay['scene_qa_source']}`; "
               f"{qa_overlay['held_raw_alerts']} raw model flags held for image review across all splits. "
               f"{qa_overlay['quality_screened_review_candidates']} remain as quality-screened review candidates."
               if qa_overlay.get("scene_qa_source") else
               "No audited scene QA overlay supplied; operational review flags have not been screened for suspected scene artefacts.")
    try:
        metrics_table = metrics_df.to_markdown(index=False, floatfmt=".5f")
    except Exception:
        metrics_table = metrics_df.to_string(index=False)
    return f'''# AgriLens — NDVI Modeling & Anomaly Screening Report

**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  
**Script version:** {SCRIPT_VERSION}  
**Input SHA-256:** `{audit['input_sha256']}`

## Executive summary

This run compares a persistence forecast (next NDVI equals the previous valid NDVI) with a Ridge regression model. The forecasting method is selected using validation fields only. It then calibrates a lower-tail residual threshold using training-only out-of-fold residuals and applies that threshold to produce review flags. The project’s original geographic field split is retained and strictly validated as 9 training fields, 6 validation fields, and 5 test fields. No random train/validation/test split or randomized cross-validation is performed.

**Selected forecast baseline:** `{manifest['selected_forecaster_from_validation']}`  
**Selected Ridge alpha:** `{alpha}`  
**Training-calibrated lower residual threshold:** `{_fmt(threshold_info['lower_anomaly_threshold'])}`  
**Held-out test *raw* anomaly flags:** {len(alerts)} across {len(fields_flagged)} field(s).

**Scene-quality integration:** {qa_note}

These are **statistical vegetation-change alerts, not confirmed crop damage or dust/drought diagnoses**. No independent damage labels were supplied for this run.

## Data and split audit

| Check | Result |
|---|---:|
| Input rows | {audit['rows_in_input']} |
| Unique fields | {audit['unique_fields']} |
| Unique parseable dates | {audit['unique_parseable_dates']} |
| Field-date duplicates | {audit['field_date_duplicate_check']} |
| Invalid NDVI values outside [-1, 1] set missing | {audit['rows_with_invalid_ndvi_outside_minus1_to_1']} |
| Rows excluded for unparseable date | {audit['rows_with_unparseable_date_excluded']} |
| Geographic fields by split | `{json.dumps(audit['geographic_split_field_counts'], ensure_ascii=False)}` |
| Rows by split | `{json.dumps(audit['geographic_split_row_counts'], ensure_ascii=False)}` |

Reference data expectations from the project summary are 615 field-date rows, 20 audited fields, and 33 dates. Actual-count checks: `{json.dumps(audit['reference_count_checks'])}`. Any mismatch should be reconciled with the data owner before final submission; this script does not edit or silently deduplicate source data.

## Forecasting evaluation

| Split | Purpose |
|---|---|
| Training | Model fitting; Ridge training errors are calculated out-of-fold by field for calibration/reporting. |
| Validation | Select Ridge alpha and choose between persistence and Ridge. |
| Test | Geographically held-out final evaluation; not used to choose the model or threshold. |

{metrics_table}

MAE and RMSE describe **forecasting error only**. They do not measure accuracy at diagnosing dust or drought.

## Anomaly method

For each field, valid NDVI observations are ordered by date. Predictors include lagged NDVI values, prior NDVI changes, time gap between observations, and day-of-year cyclical features. Where present, NDMI/dust/soil-moisture context is included only as a lagged feature. Missing values are imputed from training data within the pipeline.

Residual is defined as:

`residual = observed_NDVI - expected_NDVI`

The alert threshold is calibrated only from deterministic training-field group out-of-fold residuals. No random shuffling is used, and validation/test residuals are excluded from threshold calibration. The operational threshold is capped at zero, so a flag always means observed NDVI is lower than expected. Method: **{threshold_info['method']}**. Training OOF residual count: {threshold_info['n_training_oof_residuals']}; training fields: {threshold_info['n_training_fields']}; OOF folds: {threshold_info['n_oof_folds']}; median: {_fmt(threshold_info['residual_median'])}; robust sigma: {_fmt(threshold_info['robust_sigma'])}; 5th percentile: {_fmt(threshold_info['residual_q05'])}. A row is flagged when its residual is below the calibrated lower threshold. The threshold is statistical and is not calibrated to agronomic ground truth.

The optional `pattern_screen` distinguishes an isolated/abrupt-looking flag from repeated negative changes. This is a descriptive pattern label, not a physical cause diagnosis.

## Held-out test alerts

Flagged test fields: {', '.join(fields_flagged) if fields_flagged else 'None in this run'}. See `heldout_test_alerts.csv` for the record-level evidence and the original source columns. Every alert uses the wording **cause undetermined** and recommends review rather than an automatic irrigation action.

## Spatial GeoJSON export

The run wrote `{audit['spatial_alert_export']['output_file']}` with status `{audit['spatial_alert_export']['status']}` and {audit['spatial_alert_export']['feature_count']} mapped alert feature(s). Coordinates are interpreted strictly as WGS84 decimal-degree latitude/longitude and GeoJSON coordinates are stored in `[longitude, latitude]` order. Rows with absent or invalid coordinates are not mapped, and no coordinates or CRS transformations are fabricated. Coordinate source columns: latitude `{audit['spatial_alert_export']['latitude_column']}`, longitude `{audit['spatial_alert_export']['longitude_column']}`.

## Limitations and scientific guardrails

1. There are no independently verified dust-related or drought-related crop-damage labels in the source dataset; precision/recall for causal classification cannot be calculated.
2. Regional modeled dust is not proof that dust affected a specific field or plant. Modeled soil moisture is not a measurement of irrigation delivered to an individual field.
3. A negative NDVI residual indicates lower-than-expected greenness, not necessarily crop damage.
4. The EMIT spectral observations are from NASA EMIT and are not satellite 813 imagery. Transfer to 813 requires actual 813 data, band-response matching, and independent evaluation.
5. The model’s use of previous observations from each test field is a rolling one-step-ahead setup. Test field identities are not used to fit model coefficients, but their past observations are used as legitimate forecasting inputs.
6. Forecast scores must be reported from the current run. Do not use illustrative values or call anomaly flags validated damage labels.

## Reproducibility and files

- `field_date_ndvi_anomaly_results.csv` — source records with forecast, residual, alert, pattern, confidence, reason, and inspection-recommendation fields added as separate output columns.
- `heldout_test_alerts.csv` — only alerts from geographically held-out test fields.
- `all_split_anomaly_flags.csv` — statistical alerts across all splits (training alerts use out-of-fold Ridge predictions when Ridge is selected).
- `forecast_metrics.csv` — persistence and Ridge metrics for train OOF, validation, and test.
- `field_summary.csv` — field-level summary.
- `data_audit.json` — counts, column mappings, split audit, and source hash.
- `model_run_manifest.json` — run settings, selected model, threshold, and metrics.
- `threshold_calibration_residuals.csv` — training-only OOF residuals used for threshold calibration.
- `agrilens_spatial_alerts.geojson` — **raw** statistical flags with explicit QA status and audited WGS84 points where available.
- `quality_screened_inspection_queue.csv` — flagged observations excluding retrospective suspect-scene flags; not a verified damage set.
- `scene_qa_held_alerts.csv` — retained model alerts with scene-quality hold notes.
- `agrilens_screened_spatial_alerts.geojson` — only quality-screened review candidates with mapped audited centroids.
- `figures/` — calibration and demonstration plots, when plotting dependencies are available.

The source data is read-only; all derived artifacts are written to `{output_dir}`.
'''


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgriLens NDVI forecasting and residual anomaly screening")
    parser.add_argument("--input", default="auto", help="Path to the official audited field-date CSV/Parquet, or 'auto' for cautious repository discovery.")
    parser.add_argument("--repo-root", default=".", help="Repository root; used for auto-discovery and optional split-map discovery.")
    parser.add_argument("--output-dir", default="output/ndvi_anomaly_v1", help="Output folder; source files are not modified.")
    parser.add_argument("--field-col", default=None, help="Explicit field ID column name.")
    parser.add_argument("--date-col", default=None, help="Explicit observation date column name.")
    parser.add_argument("--ndvi-col", default=None, help="Explicit NDVI column name.")
    parser.add_argument("--split-col", default=None, help="Explicit geographic split column name.")
    parser.add_argument("--split-map", default=None, help="Existing field-to-split mapping CSV/Parquet if split is stored separately.")
    parser.add_argument("--map-field-col", default=None, help="Field ID column in --split-map.")
    parser.add_argument("--map-split-col", default=None, help="Split column in --split-map.")
    parser.add_argument("--ndmi-col", default=None, help="Optional NDMI column to add as a lagged predictor.")
    parser.add_argument("--dust-col", default=None, help="Optional modeled dust/context column to add as a lagged predictor.")
    parser.add_argument("--soil-moisture-col", default=None, help="Optional modeled soil-moisture column to add as a lagged predictor.")
    parser.add_argument("--scene-qa", default=None, help="Rama's audited date_scene_QA.csv; applies a *retrospective*, suspect-scene overlay without changing raw statistical flags.")
    parser.add_argument("--coordinate-reference", default=None, help="Rama's audited field_geography.csv with field_id, split, lat, lon (WGS84); strict one-to-one join.")
    parser.add_argument("--latitude-col", default=None, help="Optional source latitude column (WGS84 degrees) for spatial GeoJSON export.")
    parser.add_argument("--longitude-col", default=None, help="Optional source longitude column (WGS84 degrees) for spatial GeoJSON export.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_analysis(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("\nAgriLens NDVI modeling completed.")
    print(f"Input:   {result['input_path']}")
    print(f"Outputs: {result['output_dir']}")
    print(f"Selected forecast baseline: {result['manifest']['selected_forecaster_from_validation']}")
    print(f"Training-calibrated anomaly threshold: {result['manifest']['anomaly_calibration']['lower_anomaly_threshold']:.5f}")
    print(f"Held-out test anomaly flags: {result['alert_count_test']}")
    print(f"Scene QA held flags (all splits): {result['scene_qa_audit']['held_raw_alerts']}")
    print("Interpretation: anomaly screening only; dust/drought cause remains undetermined.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
