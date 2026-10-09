#!/usr/bin/env python3
"""Optional deeper audit, run where `pandas.read_parquet` and pyarrow are available.

Reads the original 707,580-row project dataset, not synthetic data; does not fit a model.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def as_json(v):
    if isinstance(v, np.generic):return v.item()
    raise TypeError(type(v).__name__)


def audit_parquet(path:Path,out:Path):
    try:
        d=pd.read_parquet(path)
    except ImportError as e:
        raise SystemExit('Optional pixel audit requires pyarrow or fastparquet; in your local venv run: pip install pyarrow') from e
    required={'pixel_id','field_id','date','x_utm','y_utm','block','split','ndvi','ndmi','evi','cropland_reference_2021','scl'}
    missing=required.difference(d.columns)
    if missing:raise ValueError('Required pixel columns missing: '+str(sorted(missing)))
    d['date']=pd.to_datetime(d.date)
    assigned=d[d.field_id.notna()].copy()
    assigned['field_id']=assigned.field_id.astype('int64').astype(str)
    stats={
      'dataset_path':str(path),
      'rows':int(len(d)),'columns':int(d.shape[1]),
      'unique_scene_dates':int(d.date.nunique()),
      'unique_pixels':int(d.pixel_id.nunique()),
      'unique_fields':int(assigned.field_id.nunique()),
      'duplicate_pixel_dates':int(d.duplicated(['pixel_id','date']).sum()),
      'nonpositive_day_intervals': int((d.days_since_prev<=0).sum()) if 'days_since_prev' in d else None,
      'field_assigned_fraction':float(d.field_id.notna().mean()),
      'cropland_reference_fraction':float(d.cropland_reference_2021.mean()),
      'evi_over_1_count':int((d.evi>1).sum()),
      'out_of_range_ndvi_count':int(((d.ndvi < -1)|(d.ndvi > 1)).sum()),
      'out_of_range_ndmi_count':int(((d.ndmi < -1)|(d.ndmi > 1)).sum()),
      'nonfinite_index_rows':int((~np.isfinite(d[['ndvi','ndmi','evi']])).any(axis=1).sum()),
    }
    for k in ['pixel_id','block']:
        s1=set(d.loc[d.split=='train',k]);s2=set(d.loc[d.split=='test',k]);stats[f'original_split_overlap_{k}']=len(s1&s2)
    tr=set(assigned.loc[assigned.split=='train','field_id']);te=set(assigned.loc[assigned.split=='test','field_id'])
    stats['original_split_overlap_fields']=sorted(tr&te)
    stats['original_split_overlap_fields_count']=len(tr&te)
    byfield=assigned.groupby('field_id').agg(
        pixel_dates=('pixel_id','size'),
        unique_pixels=('pixel_id','nunique'),
        unique_dates=('date','nunique'),
        cropland_reference_2021_fraction=('cropland_reference_2021','mean'),
        mean_ndvi=('ndvi','mean'),
        mean_evi=('evi','mean'),
        present_in_original_train=('split',lambda s:bool((s=='train').any())),
        present_in_original_test=('split',lambda s:bool((s=='test').any()))).reset_index()
    bydate=d.groupby(d.date.dt.normalize()).agg(
        valid_pixel_observations=('pixel_id','size'),
        unique_fields=('field_id','nunique'),
        median_ndvi=('ndvi','median'),
        median_evi=('evi','median')).reset_index()
    stats['largest_field_share_of_field_assigned_pixel_dates']=float(byfield.pixel_dates.max()/len(assigned))
    stats['landcover_mismatch']={
      'assigned_and_not_cropland_2021':int(((d.field_id.notna()) & (~d.cropland_reference_2021)).sum()),
      'not_assigned_and_cropland_2021':int(((d.field_id.isna()) & d.cropland_reference_2021).sum()),
    }
    out.mkdir(exist_ok=True,parents=True)
    byfield.to_csv(out/'original_pixel_field_representation.csv',index=False)
    bydate.to_csv(out/'original_pixel_date_representation.csv',index=False)
    (out/'original_pixel_deep_audit.json').write_text(json.dumps(stats,indent=2,default=as_json))
    print(json.dumps({k:stats[k] for k in ['rows','unique_pixels','unique_fields','original_split_overlap_fields_count','evi_over_1_count']},indent=2))
    return stats


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[1]/'inputs'/'dataset.parquet')
    a.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'outputs')
    opt=a.parse_args()
    audit_parquet(opt.input,opt.out)

if __name__=='__main__':main()
