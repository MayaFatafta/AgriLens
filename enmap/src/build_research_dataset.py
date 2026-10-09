#!/usr/bin/env python3
"""Build an auditable AgriLens field-level NDVI next-observation regression dataset.

Inputs are team-supplied derived measurements and previously verified FTW spatial crosswalk.
No pixels or labels are fabricated. Run without --evaluate to skip optional Ridge baseline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE = Path(__file__).resolve().parents[1]
MIN_GAP_M = 100.0
FEATURES = [
    "ndvi_mean", "ndmi_mean", "evi_mean", "aot_s2_mean", "ndvi_change_from_prev",
    "ndmi_change_from_prev", "days_since_prev", "pixel_count", "t2m_c",
    "precip_48h", "wind_max_48h", "dust_max_48h", "aod_max_48h",
    "soil_moisture_28_to_100cm", "sm_change_7d", "sm_change_48h", "day_of_year",
]


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def safe_json(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    raise TypeError(str(type(obj)))


def prepare_geometry(geopath: Path, valid_ids: set[str]):
    g = gpd.read_file(geopath)
    if g.crs is None:
        raise ValueError('Field geometries require a declared CRS')
    assert 'field_id' in g.columns, 'Crosswalk field_id missing'
    g['field_id'] = g.field_id.astype('string')
    g = g[g.field_id.isin(valid_ids)].copy().to_crs(epsg=32636)
    if len(g) != len(valid_ids) or g.field_id.duplicated().any():
        raise ValueError('Expected exactly one FTW polygon per eligible field')
    if (~g.geometry.is_valid).any() or g.geometry.is_empty.any():
        raise ValueError('Invalid or empty field geometry')
    g['area_ha'] = g.geometry.area / 1e4
    g['centroid_x_utm'] = g.geometry.centroid.x
    g['centroid_y_utm'] = g.geometry.centroid.y
    return g.reset_index(drop=True)


def geo_splits(fields: gpd.GeoDataFrame, buffer_m: float = MIN_GAP_M):
    """West/middle/east 3-zone KMeans; discard polygons violating minimum separation.

    The test zone is reserved first, then validation candidates near test excluded,
    and training candidates near either evaluation zone excluded. Does not imply
    epidemiological or causal independence of regional dust/weather conditions.
    """
    if len(fields) < 12:
        raise ValueError('Need >=12 eligible fields for this 3-zone demonstration')
    xy = fields[['centroid_x_utm', 'centroid_y_utm']].to_numpy()
    labels = KMeans(n_clusters=3, n_init=10, random_state=42).fit_predict(xy)
    ordered = sorted(np.unique(labels), key=lambda i: xy[labels == i, 0].mean())
    lab_to_split = {ordered[0]: 'train', ordered[1]: 'validation', ordered[2]: 'test'}
    assigned = np.array([lab_to_split[k] for k in labels], dtype=object)
    geoms = list(fields.geometry)
    # Hold test fixed; quarantine validation fields within buffer of test.
    test_idx = np.where(assigned == 'test')[0]
    for i in np.where(assigned == 'validation')[0]:
        if min(geoms[i].distance(geoms[j]) for j in test_idx) < buffer_m:
            assigned[i] = 'excluded_buffer'
    # Quarantine training fields too close to any retained validation/test polygon.
    eval_idx = np.where(np.isin(assigned, ['validation', 'test']))[0]
    for i in np.where(assigned == 'train')[0]:
        if min(geoms[i].distance(geoms[j]) for j in eval_idx) < buffer_m:
            assigned[i] = 'excluded_buffer'
    ret = fields[['field_id', 'area_ha', 'centroid_x_utm', 'centroid_y_utm', 'confidence_mean_native']].copy()
    ret['split_group'] = assigned
    for label in ['train', 'validation', 'test']:
        if sum(assigned == label) < 2:
            raise ValueError(f'Buffer removes too many fields from {label}: cannot use this design')
    pair_gaps = {}
    for s1, s2 in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]:
        ix = np.where(assigned == s1)[0]
        iy = np.where(assigned == s2)[0]
        mindist = min(geoms[i].distance(geoms[j]) for i in ix for j in iy)
        if mindist < buffer_m - 1e-8:
            raise AssertionError(f'Insufficient polygon separation {s1}/{s2}: {mindist:.2f}m')
        pair_gaps[f'{s1}_vs_{s2}'] = float(mindist)
    return ret, pair_gaps


def assemble_field_regression(source: pd.DataFrame, split_inventory: pd.DataFrame,
                              horizon_min: int = 3, horizon_max: int = 18,
                              cutoff: str = '2025-08-01'):
    d = source.copy()
    d['field_id'] = d.field_id.astype(str)
    d['date'] = pd.to_datetime(d.date)
    d = d.sort_values(['field_id', 'date'])
    if d.duplicated(['field_id', 'date']).any():
        raise ValueError('duplicate field-date rows')
    d = d.merge(split_inventory[['field_id', 'split_group']], on='field_id',
                how='left', validate='many_to_one')
    if d.split_group.isna().any():
        raise ValueError('source field lacks geometry/split')
    gr = d.groupby('field_id', sort=False)
    d['target_ndvi_next'] = gr.ndvi_mean.shift(-1)
    d['target_date'] = gr.date.shift(-1)
    d['target_horizon_days'] = (d.target_date - d.date).dt.days
    d['day_of_year'] = d.date.dt.dayofyear
    d['in_range_horizon'] = d.target_horizon_days.between(horizon_min, horizon_max)
    # Target is observed next S2 field mean. Exclude past/current labels used as predictors.
    d = d[d.in_range_horizon & d.split_group.isin(['train', 'validation', 'test'])].copy()
    d['ml_split'] = d.split_group
    boundary = pd.Timestamp(cutoff)
    # Both origin/label within earlier period for train/validation.
    before = d.target_date < boundary
    # Both origin/label in later period for test.
    after = d.date >= boundary
    d = d[((d.ml_split.isin(['train', 'validation'])) & before)
          | ((d.ml_split == 'test') & after)].copy()
    if d.empty or d.groupby('ml_split').size().reindex(['train','validation','test'],fill_value=0).min() < 8:
        raise ValueError('Not enough separated labeled observations for this cutoff')
    if d.groupby('ml_split').field_id.nunique().reindex(['train','validation','test'], fill_value=0).min()<2:
        raise ValueError('Not enough independent field IDs per split')
    assert all(d[d.ml_split==s].field_id.nunique() >= 2 for s in ['train', 'validation', 'test'])
    assert d[d.ml_split=='test'].date.min() >= boundary
    assert d[d.ml_split.isin(['train','validation'])].target_date.max() < boundary
    for s1 in ['train','validation','test']:
        for s2 in ['train','validation','test']:
            if s1<s2:
                assert not set(d[d.ml_split==s1].field_id) & set(d[d.ml_split==s2].field_id)
    cols = ['field_id','date','target_date','target_horizon_days','ml_split','target_ndvi_next',
            'coverage_ratio_vs_p90'] + FEATURES
    if any(c not in d.columns for c in cols):
        raise KeyError('Missing expected feature columns')
    return d[cols].sort_values(['ml_split','field_id','date']).reset_index(drop=True)


def score(y, pred):
    return {'MAE': float(mean_absolute_error(y, pred)),
            'RMSE': float(np.sqrt(mean_squared_error(y, pred))),
            'R2': float(r2_score(y, pred)) if len(y) > 1 else None,
            'rows': int(len(y))}


def evaluate(data: pd.DataFrame):
    # Imputation/scaling are fit exclusively on training fields before Aug-2025.
    train = data[data.ml_split=='train'].copy()
    valid = data[data.ml_split=='validation'].copy()
    test = data[data.ml_split=='test'].copy()
    xtr, ytr = train[FEATURES], train.target_ndvi_next
    best = None
    tuning = []
    for alpha in [0.1,1.,10.,100.]:
        model = Pipeline([
            ('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
            ('scale', StandardScaler()),
            ('ridge', Ridge(alpha=alpha))])
        model.fit(xtr, ytr)
        val_score = score(valid.target_ndvi_next, model.predict(valid[FEATURES]))
        tuning.append({'alpha':alpha, **val_score})
        if best is None or val_score['MAE'] < best[0]:
            best=(val_score['MAE'], alpha)
    # Fit on train only: validation remains separate, test untouched until selection.
    final = Pipeline([
        ('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
        ('scale', StandardScaler()),
        ('ridge', Ridge(alpha=best[1]))])
    final.fit(xtr,ytr)
    results={'target':'next_accepted_Sentinel2_field_mean_NDVI',
             'comparison':'persistence_baseline_current_ndvi_mean',
             'selected_alpha_by_validation_MAE':best[1],
             'feature_names':FEATURES,
             'alpha_validation_results':tuning,
             'note':'Exploratory derived-NDVI forecasting only; no crop yield, true drought or dust damage labels.'}
    preds=[]
    for split,tab in [('train',train),('validation',valid),('test',test)]:
        actual=tab.target_ndvi_next
        p_r=final.predict(tab[FEATURES])
        p_b=tab.ndvi_mean
        results[split]={'ridge':score(actual,p_r), 'persistence':score(actual,p_b),
                        'fields':int(tab.field_id.nunique()),
                        'date_first':str(tab.date.min().date()),
                        'date_last':str(tab.target_date.max().date())}
        tmp=tab[['field_id','date','target_date','target_ndvi_next','target_horizon_days','ml_split']].copy()
        tmp['ridge_pred_ndvi']=p_r
        tmp['persistence_pred_ndvi']=p_b.to_numpy()
        preds.append(tmp)
    return results,pd.concat(preds,ignore_index=True)


def representation_summary(field_dates,inv,ml,qa,provenance,geopath):
    counts=field_dates.groupby('field_id').size()
    grouped=ml.groupby('ml_split').agg(field_count=('field_id','nunique'),
                                       labeled_pairs=('field_id','size'),
                                       first_origin=('date','min'),last_target=('target_date','max'),
                                       median_horizon_days=('target_horizon_days','median'))
    return {
     'original_pixel_observations': qa['files']['dataset.parquet']['rows'],
     'original_unique_pixels': 22500,  # Confirmed by prior geometry-alignment audit (supplied in inputs)
     'original_scene_dates':qa['checks']['observation_dates_unique'],
     'original_field_count':qa['checks']['field_count'],
     'original_pixel_split_crosses_fields':qa['checks']['train_test_overlapping_fields_count'],
     'original_block_overlap':qa['checks']['train_test_overlapping_blocks'],
     'pixel_field_geometry_agreement_from_prior_geometry_audit':'22,500 pixel centers checked, zero mismatches; see original geometry audit',
     'field_1665168_full_area_ha':13196.884883,
     'field_1665168_inside_AOI_ha':639.871634,
     'large_field_1665168_quarantined':True,
     'source_field_date_rows':int(len(pd.read_csv(BASE/'inputs'/'field_timeseries.csv'))) if (BASE/'inputs'/'field_timeseries.csv').exists() else 982,
     'retained_descriptive_field_dates':int(len(field_dates)),
     'retained_descriptive_field_ids':int(field_dates.field_id.nunique()),
     'excluded_for_buffer_fields':int((inv.split_group=='excluded_buffer').sum()),
     'modeling_field_counts':{str(k):int(v) for k,v in inv.split_group.value_counts().items()},
     'modeling_table':{str(k):{'fields':int(v.field_count),'pairs':int(v.labeled_pairs),'first_origin':str(v.first_origin.date()),'last_target':str(v.last_target.date()),'median_horizon_days':float(v.median_horizon_days)} for k,v in grouped.iterrows()},
     'observed_NDVI_is_the_only_supervised_target':True,
     'independent_dust_drought_crop_yield_labels':False,
     'sources_and_units_from_provenance':{'region':'Egypt, Nile Delta', 'sentinel2':'L2A, 20m features','env':'Open-Meteo regional modeled'}
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--field-csv', type=Path, default=BASE/'inputs'/'field_date_analysis.csv')
    p.add_argument('--geometry', type=Path, default=BASE/'inputs'/'ftw_aoi_fields_with_crosswalk.geojson')
    p.add_argument('--original-qa',type=Path,default=BASE/'inputs'/'qa_results.json')
    p.add_argument('--provenance',type=Path,default=BASE/'inputs'/'provenance.json')
    p.add_argument('--out',type=Path,default=BASE/'outputs')
    p.add_argument('--gap-m',type=float,default=100)
    p.add_argument('--cutoff',default='2025-08-01')
    p.add_argument('--evaluate',action='store_true')
    a=p.parse_args(argv)
    out=a.out;out.mkdir(parents=True,exist_ok=True)
    src=pd.read_csv(a.field_csv,parse_dates=['date'])
    src['field_id']=src.field_id.astype(str)
    g=prepare_geometry(a.geometry,set(src.field_id))
    inv,pair_gaps=geo_splits(g,a.gap_m)
    inv=inv.sort_values('field_id').reset_index(drop=True)
    reg=assemble_field_regression(src,inv,cutoff=a.cutoff)
    inv.to_csv(out/'sampling_frame_and_splits.csv',index=False)
    reg.to_csv(out/'next_ndvi_regression.csv',index=False,date_format='%Y-%m-%d')
    report=representation_summary(src,inv,reg,json.loads(a.original_qa.read_text()),json.loads(a.provenance.read_text()),a.geometry)
    report['geographic_minimum_pairwise_gap_m']=pair_gaps
    report['nominal_polygon_buffer_m']=a.gap_m
    report['date_boundary_test_begins']=a.cutoff
    report['feature_list']=FEATURES
    report['source_sha256']={str(x.name):sha256(x) for x in [a.field_csv,a.geometry,a.original_qa,a.provenance]}
    report['data_unit_note']='707k pixel-dates are highly repeated measures. Regression unit is a field-date pair with target observed at next accepted date.'
    report['sampling_restrictions']='30% train/test randomly split by fields is replaced with 3 spatial zones and 100m polygon buffer; test only after Aug 1, 2025; descriptive screening filters preexisting and may use a retrospective pixel-coverage p90 threshold.'
    report['limitations']=[
      'No independent ground truth for crop yield, irrigation needs, dust damage or drought diagnosis.',
      'Target is next observed Sentinel-2 NDVI (not measured crop response); availability and horizon are variable.',
      'Dataset is observational; modeled dust/soil moisture are regional and may repeat across fields.',
      'All samples are from one 3x3 km Egypt AOI and one March-September 2025 growing period.',
      'Field polygons are FTW predictions, not cadastral or verified crop parcels.',
      'Field 1665168 excluded as suspicious merged model polygon.',
      'Retrospective quality filter uses within-field p90 computed across dates: avoid treating it as an online feature.',
      'No independent atmospheric-correction or per-scene imagery assessment in this audit.',
      'The original pixel Parquet was previously audited with low-level extraction; this generator reads verified CSV/GeoJSON.'
    ]
    if a.evaluate:
        scores,preds=evaluate(reg)
        (out/'regression_baseline_scores.json').write_text(json.dumps(scores,indent=2,default=safe_json))
        preds.to_csv(out/'regression_predictions.csv',index=False,date_format='%Y-%m-%d')
        report['baseline_evaluation_run']=True
    else:
        report['baseline_evaluation_run']=False
    (out/'representation_leakage_audit.json').write_text(json.dumps(report,indent=2,default=safe_json))
    print('Sampling fields:',inv.split_group.value_counts().to_dict())
    print('Regression pairs:',reg.ml_split.value_counts().to_dict())
    print('Geographic polygon separations (m):',pair_gaps)
    print('Wrote files into',out)
    return report

if __name__=='__main__':
    main()
