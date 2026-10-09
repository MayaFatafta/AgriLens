#!/usr/bin/env python3
"""Auditable, manually configured *proxy screening* of real Egyptian AgriLens data.

NO supervised training, synthetic rows, verified damage labels or causal inference.
Runs with pandas and numpy only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_COLUMNS = [
    'field_id', 'date', 'ndvi_mean', 'ndmi_mean', 'pixel_count',
    'coverage_ratio_vs_p90', 'low_coverage', 'quarantined_polygon',
    'dust_max_48h', 'aod_max_48h', 'soil_moisture_28_to_100cm',
]
MASTER_COLUMNS = ['field_id', 'field_split']
SPLITS = ('train', 'validation', 'test')


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def clean_ids(series: pd.Series) -> pd.Series:
    result = pd.to_numeric(series, errors='coerce')
    if result.isna().any() or (~np.isfinite(result.to_numpy(dtype=float))).any():
        raise ValueError('Null, nonnumeric, or nonfinite field_id in a required input.')
    if ((result % 1) != 0).any():
        raise ValueError('A field_id is not an integer.')
    return result.astype('int64')


def parse_bool(series: pd.Series, name: str) -> pd.Series:
    mapping = {'true': True, 'false': False, '1': True, '0': False, 'yes': True, 'no': False}
    val = series.astype('string').str.strip().str.lower().map(mapping)
    if val.isna().any():
        raise ValueError(f'{name} contains an invalid or missing boolean value.')
    return val.astype(bool)


def analyze(
    field_dates: pd.DataFrame,
    master: pd.DataFrame,
    hsi: pd.DataFrame | None = None,
    ndvi_drop: float = -0.08,
    ndmi_drop: float = -0.03,
    max_gap_days: int = 15,
) -> dict:
    """Return computed dataframes and report. Train dates alone fit environment cutoffs."""
    if not -1 < ndvi_drop < 0 or not -1 < ndmi_drop < 0 or max_gap_days < 1:
        raise ValueError('Invalid predeclared decline thresholds or max gap.')

    for name, df, required in [
        ('field_dates', field_dates, SOURCE_COLUMNS),
        ('master', master, MASTER_COLUMNS),
    ]:
        missing = sorted(set(required) - set(df.columns))
        if missing:
            raise ValueError(f'{name} missing required columns: {missing}')

    raw = field_dates.copy()
    fields = master.copy()
    raw['field_id'] = clean_ids(raw['field_id'])
    fields['field_id'] = clean_ids(fields['field_id'])
    if fields.field_id.duplicated().any():
        raise ValueError('Duplicate field_id in audited master table.')
    if not fields['field_split'].isin(SPLITS).all():
        raise ValueError('Unexpected audited geographic field_split.')
    raw['date'] = pd.to_datetime(raw['date'], errors='coerce')
    if raw['date'].isna().any():
        raise ValueError('Invalid observation date.')
    if raw.duplicated(['field_id', 'date']).any():
        raise ValueError('Duplicate field_id + date. Resolve before screening.')
    raw_count = len(raw)
    raw_field_count = raw.field_id.nunique()

    # Spatially audited field_split is authoritative; NEVER use raw 'split'.
    out = raw.merge(fields[MASTER_COLUMNS], on='field_id', how='inner', validate='many_to_one')
    if out.empty or not (out.field_split == 'train').any():
        raise ValueError('No matching eligible training fields in source data.')
    if 'split' in out.columns:
        out = out.rename(columns={'split': 'historical_split_recorded'})
        out['split_mismatch_with_audited'] = (
            out['historical_split_recorded'].astype('string') != out['field_split'].astype('string')
        ).fillna(True)
    else:
        out['historical_split_recorded'] = pd.NA
        out['split_mismatch_with_audited'] = False

    out['low_coverage'] = parse_bool(out['low_coverage'], 'low_coverage')
    out['quarantined_polygon'] = parse_bool(out['quarantined_polygon'], 'quarantined_polygon')
    numerical = [
        'ndvi_mean', 'ndmi_mean', 'pixel_count', 'coverage_ratio_vs_p90',
        'dust_max_48h', 'aod_max_48h', 'soil_moisture_28_to_100cm',
    ]
    for col in numerical:
        out[col] = pd.to_numeric(out[col], errors='coerce')
    # Reject impossible auxiliary measurements rather than treating them as risk.
    sm = out['soil_moisture_28_to_100cm'].dropna()
    if (~np.isfinite(sm)).any() or ((sm < 0) | (sm > 1)).any():
        raise ValueError('Modeled volumetric soil moisture must be finite and within [0,1].')
    for name in ['dust_max_48h', 'aod_max_48h']:
        measured = out[name].dropna()
        if (~np.isfinite(measured)).any() or (measured < 0).any():
            raise ValueError(f'{name} must be finite and nonnegative.')

    if out[['ndvi_mean', 'ndmi_mean']].notna().all(axis=1).sum() == 0:
        raise ValueError('No valid vegetation observations in eligible fields.')
    if ((out['coverage_ratio_vs_p90'].dropna() < 0) |
        (out['coverage_ratio_vs_p90'].dropna() > 1.5)).any():
        raise ValueError('Unexpected coverage ratios.')
    if (out['pixel_count'].dropna() < 0).any():
        raise ValueError('Negative pixel counts.')

    # Every daily environment value is repeated across fields. Train cutoffs are
    # calibrated by DISTINCT calendar date, never by duplicated field-date rows.
    env_cols = ['dust_max_48h', 'aod_max_48h', 'soil_moisture_28_to_100cm']
    max_variation_per_date = {c: int(out.groupby('date')[c].nunique(dropna=True).max())
                              for c in env_cols}
    if any(v > 1 for v in max_variation_per_date.values()):
        raise ValueError('Environmental context is inconsistent between fields on the same date; audit first.')

    train_days = (out.loc[out.field_split == 'train', ['date'] + env_cols]
                  .drop_duplicates(subset=['date']).sort_values('date').copy())
    dust_train = train_days['dust_max_48h'].dropna()
    sm_train = train_days['soil_moisture_28_to_100cm'].dropna()
    aod_train = train_days['aod_max_48h'].dropna()
    if len(dust_train) < 2 or len(sm_train) < 2:
        raise ValueError('Insufficient distinct training dates with modeled dust/soil moisture.')

    thresholds = {
        'dust_max_48h_high_train_unique_date_q75': float(dust_train.quantile(.75)),
        'soil_moisture_28_to_100cm_low_train_unique_date_q25': float(sm_train.quantile(.25)),
        'aod_max_48h_high_train_unique_date_q75_context_only': (
            float(aod_train.quantile(.75)) if len(aod_train) >= 2 else None
        ),
        'ndvi_decline_between_accepted_observations': float(ndvi_drop),
        'ndmi_decline_between_accepted_observations': float(ndmi_drop),
        'maximum_observation_gap_days': int(max_gap_days),
        'training_distinct_dates_used_for_dust': int(len(dust_train)),
        'training_distinct_dates_used_for_soil_moisture': int(len(sm_train)),
        'fitted_on': 'audited train fields, unique calendar dates only; never validation/test',
        'note': 'Exploratory heuristic cutoffs, NOT agronomic injury thresholds',
    }

    out = out.sort_values(['field_id', 'date']).reset_index(drop=True)
    out['previous_observation_date'] = out.groupby('field_id')['date'].shift(1)
    out['days_since_previous_observation'] = (
        out['date'] - out['previous_observation_date']
    ).dt.days
    out['delta_ndvi_recomputed'] = out.groupby('field_id')['ndvi_mean'].diff()
    out['delta_ndmi_recomputed'] = out.groupby('field_id')['ndmi_mean'].diff()
    out['temporal_pair_usable'] = (
        out['days_since_previous_observation'].between(1, max_gap_days)
        & out['delta_ndvi_recomputed'].notna()
        & out['delta_ndmi_recomputed'].notna()
    )
    out['source_observation_quality_ok'] = (
        ~out['low_coverage'] & ~out['quarantined_polygon']
        & out['ndvi_mean'].between(-1, 1)
        & out['ndmi_mean'].between(-1, 1)
        & out['pixel_count'].gt(0)
    )

    quality = out['source_observation_quality_ok']
    # Daily modeled environmental CONTEXT; not independent field-specific evidence.
    out['high_modeled_dust_context'] = (
        quality & out['dust_max_48h'].ge(thresholds['dust_max_48h_high_train_unique_date_q75'])
    )
    out['low_modeled_deep_soil_moisture_context'] = (
        quality & out['soil_moisture_28_to_100cm'].le(
            thresholds['soil_moisture_28_to_100cm_low_train_unique_date_q25'])
    )
    out['high_modeled_aod_context'] = (
        quality & out['aod_max_48h'].ge(thresholds['aod_max_48h_high_train_unique_date_q75_context_only'])
        if thresholds['aod_max_48h_high_train_unique_date_q75_context_only'] is not None
        else False
    )
    out['vegetation_decline_detected'] = (
        quality & out['temporal_pair_usable']
        & out['delta_ndvi_recomputed'].le(ndvi_drop)
    )
    out['ndmi_decline_detected'] = (
        quality & out['temporal_pair_usable']
        & out['delta_ndmi_recomputed'].le(ndmi_drop)
    )
    out['possible_moisture_stress_proxy'] = (
        out['low_modeled_deep_soil_moisture_context'] & out['ndmi_decline_detected']
    )
    out['dust_and_vegetation_decline_cooccurrence'] = (
        out['high_modeled_dust_context'] & out['vegetation_decline_detected']
    )
    out['moisture_and_vegetation_decline_cooccurrence'] = (
        out['possible_moisture_stress_proxy'] & out['vegetation_decline_detected']
    )
    out['multiple_stress_indicators'] = (
        out['high_modeled_dust_context'] & out['possible_moisture_stress_proxy']
    )

    out['screening_category'] = 'insufficient_input_evidence'
    sufficiently_measured = (
        quality & out['temporal_pair_usable']
        & out['dust_max_48h'].notna() & out['soil_moisture_28_to_100cm'].notna()
    )
    out.loc[sufficiently_measured, 'screening_category'] = 'no_detected_screening_indicator'
    # Context may still be screened if no temporal baseline is available.
    valid_context = quality & out['dust_max_48h'].notna()
    out.loc[valid_context & out['high_modeled_dust_context'], 'screening_category'] = 'high_modeled_dust_exposure_context'
    out.loc[quality & out['low_modeled_deep_soil_moisture_context'], 'screening_category'] = 'low_modeled_moisture_context'
    out.loc[out['possible_moisture_stress_proxy'], 'screening_category'] = 'possible_moisture_stress_proxy'
    out.loc[out['vegetation_decline_detected'], 'screening_category'] = 'vegetation_decline_detected'
    out.loc[out['moisture_and_vegetation_decline_cooccurrence'], 'screening_category'] = 'vegetation_decline_with_moisture_context'
    out.loc[out['dust_and_vegetation_decline_cooccurrence'], 'screening_category'] = 'vegetation_decline_with_dust_context'
    out.loc[out['multiple_stress_indicators'], 'screening_category'] = 'multiple_stress_indicators'
    out.loc[~quality, 'screening_category'] = 'insufficient_observation_quality'
    # Safeguard: no context or temporal delta => don't call a negative observation.
    out.loc[
        (out['screening_category'] == 'no_detected_screening_indicator') & ~sufficiently_measured,
        'screening_category'
    ] = 'insufficient_input_evidence'

    out['screening_review_priority'] = 'none'
    out.loc[
        out['high_modeled_dust_context'] | out['possible_moisture_stress_proxy']
        | out['vegetation_decline_detected'], 'screening_review_priority'
    ] = 'medium'
    out.loc[
        out['dust_and_vegetation_decline_cooccurrence']
        | out['moisture_and_vegetation_decline_cooccurrence']
        | out['multiple_stress_indicators'], 'screening_review_priority'
    ] = 'high'
    out['damage_label_verified'] = False
    out['verified_crop_damage_label'] = pd.NA
    out['label_status'] = 'NOT_VERIFIED_PROXY_ONLY'
    out['environmental_context_spatial_scope'] = 'AOI-level model, repeated by observation date'
    out['risk_interpretation'] = 'contemporaneous screening indicators; no attribution or causality'
    out['previous_observation_date'] = out['previous_observation_date'].dt.strftime('%Y-%m-%d')
    out['date'] = out['date'].dt.strftime('%Y-%m-%d')

    flags = [
        'vegetation_decline_detected', 'high_modeled_dust_context',
        'low_modeled_deep_soil_moisture_context', 'high_modeled_aod_context',
        'ndmi_decline_detected', 'possible_moisture_stress_proxy',
        'dust_and_vegetation_decline_cooccurrence',
        'moisture_and_vegetation_decline_cooccurrence',
        'multiple_stress_indicators',
    ]
    by_split = out.groupby('field_split', observed=True).agg(
        field_date_records=('field_id', 'size'),
        distinct_fields=('field_id', 'nunique'),
        distinct_dates=('date', 'nunique'),
        high_review_priority=('screening_review_priority', lambda s: int((s == 'high').sum())),
        medium_review_priority=('screening_review_priority', lambda s: int((s == 'medium').sum())),
        insufficient_temporal_pairs=('temporal_pair_usable', lambda s: int((~s).sum())),
    )
    for flag in flags:
        by_split[flag] = out.groupby('field_split')[flag].sum().astype(int)
    by_split = by_split.reset_index()

    # Aggregate modeled exposure by unique date to avoid implying fields are independent.
    by_date = (out.groupby('date').agg(
        distinct_fields=('field_id', 'nunique'),
        dust_max_48h=('dust_max_48h', 'first'),
        aod_max_48h=('aod_max_48h', 'first'),
        soil_moisture_28_to_100cm=('soil_moisture_28_to_100cm', 'first'),
        fields_with_vegetation_decline=('vegetation_decline_detected', 'sum'),
        fields_with_dust_decline_cooccurrence=('dust_and_vegetation_decline_cooccurrence', 'sum'),
        fields_with_moisture_decline_cooccurrence=('moisture_and_vegetation_decline_cooccurrence', 'sum'),
        fields_with_high_review_priority=('screening_review_priority', lambda s: (s == 'high').sum()),
    ).reset_index())

    queue = out[out.screening_review_priority.isin(['high', 'medium'])].copy()
    queue['priority_rank'] = queue.screening_review_priority.map({'high': 0, 'medium': 1})
    queue = queue.sort_values(['priority_rank', 'date', 'field_id']).drop(columns=['priority_rank'])
    queue_cols = [
        'field_id', 'field_split', 'date', 'previous_observation_date',
        'days_since_previous_observation', 'screening_review_priority',
        'screening_category', 'ndvi_mean', 'ndmi_mean', 'delta_ndvi_recomputed',
        'delta_ndmi_recomputed', 'dust_max_48h', 'aod_max_48h',
        'soil_moisture_28_to_100cm', 'vegetation_decline_detected',
        'high_modeled_dust_context', 'possible_moisture_stress_proxy',
        'dust_and_vegetation_decline_cooccurrence',
        'moisture_and_vegetation_decline_cooccurrence',
        'label_status',
    ]
    queue = queue[queue_cols]

    # Tie the one-day EMIT/Sentinel-2 context ONLY to each genuine matched date.
    matched = pd.DataFrame()
    if hsi is not None:
        expect = ['field_id', 'field_split', 's2_observation_date', 'emit_acquired_utc',
                  'emit_scene_id', 'emit_valid_pixel_count',
                  'emit_quality_coverage_fraction', 'emit_ndvi_median',
                  'emit_ndre_median', 'emit_ndmi_median']
        missing = sorted(set(expect) - set(hsi.columns))
        if missing:
            raise ValueError(f'hsi missing columns: {missing}')
        usable = hsi.copy()
        usable['field_id'] = clean_ids(usable['field_id'])
        usable['s2_observation_date'] = pd.to_datetime(
            usable['s2_observation_date'], errors='coerce'
        ).dt.strftime('%Y-%m-%d')
        if usable.duplicated(['field_id', 's2_observation_date']).any():
            raise ValueError('Duplicate field-date records in HSI table.')
        if not set(usable.field_id).issubset(set(fields.field_id)):
            raise ValueError('HSI table contains an unaudited field.')
        verified_split = usable.merge(fields[MASTER_COLUMNS], on='field_id', suffixes=('_hsi','_audit'), validate='many_to_one')
        if not verified_split.field_split_hsi.eq(verified_split.field_split_audit).all():
            raise ValueError('HSI split conflicts with authoritative master split.')
        merged = usable.merge(
            out[['field_id', 'date', 'field_split', 'screening_category',
                 'screening_review_priority', 'high_modeled_dust_context',
                 'low_modeled_deep_soil_moisture_context',
                 'vegetation_decline_detected', 'possible_moisture_stress_proxy',
                 'damage_label_verified', 'label_status']],
            left_on=['field_id', 's2_observation_date'], right_on=['field_id', 'date'],
            how='left', validate='one_to_one', suffixes=('_hsi', '_screening')
        )
        if merged['screening_category'].isna().any():
            raise ValueError('A usable HSI field lacks matching S2 date screening data.')
        matched = merged.drop(columns=['date'])

    distribution = out['screening_category'].value_counts().sort_index().to_dict()
    report = {
        'status': 'EXPLORATORY_PROXY_RISK_SCREENING_NOT_DAMAGE_CLASSIFICATION',
        'input_field_date_records': raw_count,
        'input_distinct_field_ids': int(raw_field_count),
        'audited_eligible_fields': int(fields.field_id.nunique()),
        'screened_field_date_records': int(len(out)),
        'screened_fields': int(out.field_id.nunique()),
        'screened_dates': int(out.date.nunique()),
        'excluded_rows_outside_eligible_field_ids': int(raw_count - len(out)),
        'historical_vs_audited_split_conflict_records': int(out.split_mismatch_with_audited.sum()),
        'recomputed_temporal_pair_usable': int(out.temporal_pair_usable.sum()),
        'screening_review_queue_records': int(len(queue)),
        'high_priority_records': int((out.screening_review_priority == 'high').sum()),
        'category_counts': {str(k): int(v) for k, v in distribution.items()},
        'proxy_flag_counts': {f: int(out[f].sum()) for f in flags},
        'thresholds': thresholds,
        'distinct_model_context_values_max_per_date': max_variation_per_date,
        'hsi_single_scene_field_matches': int(len(matched)),
        'verified_independent_crop_damage_labels': 0,
        'supervised_damage_classification_ready': False,
        'known_limitations': [
            'No independently confirmed crop damage or cause labels.',
            'Dust/AOD/deep soil moisture are modeled AOI-level daily covariates repeated across fields.',
            'Dust 48h and vegetation changes coexist in time; dust causation/sequence cannot be inferred.',
            'NDVI/NDMI declines can reflect growth stage, crop harvest, irrigation, management, disease or noise.',
            'Drought cannot be confirmed from modeled deep soil moisture alone; narrow quantized range.',
            'Cutoffs are exploratory, non-agronomic heuristic thresholds.',
            'Historical S2 field-date table is filtered to 20 independently audited field IDs.',
            'EMIT 14-field single-date match has strong coverage/selection bias and adds no damage labels.',
        ],
    }
    return {'screened': out, 'by_split': by_split, 'by_date': by_date,
            'review_queue': queue, 'hsi_context': matched, 'report': report}


def main() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field-dates', type=Path, default=package_root / 'inputs/field_date_analysis.csv')
    parser.add_argument('--master', type=Path, default=package_root / 'inputs/egypt_emit_s2_field_alignment.csv')
    parser.add_argument('--hsi', type=Path, default=package_root / 'inputs/egypt_hsi_s2_usable_fields.csv',
                        help='Optional HSI matched-field table (default bundled).')
    parser.add_argument('--output', type=Path, default=package_root / 'outputs')
    parser.add_argument('--ndvi-drop', type=float, default=-0.08)
    parser.add_argument('--ndmi-drop', type=float, default=-0.03)
    parser.add_argument('--max-gap-days', type=int, default=15)
    args = parser.parse_args()

    data = pd.read_csv(args.field_dates)
    master = pd.read_csv(args.master)
    hsi = pd.read_csv(args.hsi) if args.hsi.is_file() else None
    results = analyze(data, master, hsi, args.ndvi_drop, args.ndmi_drop, args.max_gap_days)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    names = {
        'screened': 'egypt_field_date_proxy_screening.csv',
        'by_split': 'screening_by_geographic_split.csv',
        'by_date': 'screening_by_unique_date.csv',
        'review_queue': 'manual_field_review_queue.csv',
        'hsi_context': 'emit_s2_same_date_descriptive_context.csv',
    }
    for key, name in names.items():
        results[key].to_csv(out / name, index=False)
    report = results['report']
    report['source_inputs_sha256'] = {
        'field_dates': file_sha256(args.field_dates),
        'audited_master': file_sha256(args.master),
        'matched_hsi': file_sha256(args.hsi) if args.hsi.is_file() else None,
    }
    report['outputs'] = names
    (out / 'proxy_screening_audit.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({
        'status': report['status'],
        'input_field_date_records': report['input_field_date_records'],
        'screened_field_date_records': report['screened_field_date_records'],
        'screened_fields': report['screened_fields'],
        'matched_hsi_fields': report['hsi_single_scene_field_matches'],
        'screening_review_queue_records': report['screening_review_queue_records'],
        'high_priority_records': report['high_priority_records'],
        'verified_crop_damage_labels': 0,
        'outputs_dir': str(out.resolve()),
    }, indent=2))

if __name__ == '__main__':
    main()
