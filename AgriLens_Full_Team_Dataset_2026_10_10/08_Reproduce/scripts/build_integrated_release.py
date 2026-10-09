#!/usr/bin/env python3
"""Build AgriLens real-only additive enhancement and QA-gated temporal feature table.

Usage:
  python scripts/build_integrated_release.py --base REAL_SCREENING.csv --v2 V2_REAL_TIDY.csv --emit-zip FROZEN_EMIT.zip --out DIRECTORY

No synthetic or verified crop damage labels are created. Does NOT overwrite originals.
Requires pandas and numpy. Reuses audited additive merge procedure bundled in script folder.
"""
import argparse
from pathlib import Path
import csv
import hashlib
import json
import shutil
from zipfile import ZipFile
import numpy as np
import pandas as pd
from merge_verified_features import merge

KEYS=['field_id','date']
ADDED=['v2_ndvi_slope3_total','v2_ndvi_dev_from_prev5_median','v2_cusum_neg']
QA_FEATURES=['qa_ndvi_slope3_total','qa_ndvi_dev_from_prev5_median','qa_cusum_neg_reset']


def sha256(path):
    d=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            d.update(b)
    return d.hexdigest()


def truth_values(series):
    if pd.api.types.is_bool_dtype(series):
        if series.isna().any(): raise ValueError('Missing quality boolean')
        return series.astype(bool)
    as_text=series.astype('string').str.lower().str.strip()
    mapping={'true': True,'false':False,'1':True,'0':False}
    converted=as_text.map(mapping)
    if converted.isna().any():
        raise ValueError('Invalid source observation quality flags')
    return converted.astype(bool)


def apply_qa_windows(enhanced):
    """Use only current/past quality-valid observations and <=15-day consecutive gaps.

    The added raw v2 columns are not modified. qa_* versions are intended for
    subsequent model experiments, and are missing when history fails QA.
    CUSUM (allowance 0.01 NDVI units) resets on invalid pair or long gap.
    """
    df=enhanced.copy()
    if not {'source_observation_quality_ok','field_id','date','ndvi_mean'} <= set(df):
        raise ValueError('Missing required original quality/history data')
    df['_original_row_number']=np.arange(len(df))
    df['date']=pd.to_datetime(df['date'],errors='raise')
    df['_quality_valid']=truth_values(df['source_observation_quality_ok'])
    df=df.sort_values(['field_id','date']).copy()
    for x in QA_FEATURES:
        df[x]=np.nan
    for x in ['qa_temporal_pair_ok','qa_window3_ok','qa_window_prev5_ok']:
        df[x]=False

    for fid, part in df.groupby('field_id',sort=False):
        ix=part.index.to_list()
        dates=part['date'].tolist()
        ndvi=part['ndvi_mean'].to_numpy(float)
        ok=part['_quality_valid'].to_numpy(bool)
        prev_gap_ok=np.zeros(len(ix),dtype=bool)
        for j in range(1,len(ix)):
            days=(dates[j]-dates[j-1]).days
            prev_gap_ok[j]= 1 <= days <=15
        cusum=0.0
        for j,row_ix in enumerate(ix):
            pair=j>=1 and ok[j] and ok[j-1] and prev_gap_ok[j] and np.isfinite(ndvi[j]) and np.isfinite(ndvi[j-1])
            df.at[row_ix,'qa_temporal_pair_ok']=bool(pair)
            if pair:
                # One-sided CUSUM; 0.01 allowable upward drift per step.
                cusum=min(0.0,cusum+(ndvi[j]-ndvi[j-1])+0.01)
                df.at[row_ix,'qa_cusum_neg_reset']=cusum
            else:
                cusum=0.0
            window3 = (j>=2 and ok[j-2:j+1].all() and prev_gap_ok[j-1:j+1].all()
                       and np.isfinite(ndvi[j-2:j+1]).all())
            df.at[row_ix,'qa_window3_ok']=bool(window3)
            if window3:
                df.at[row_ix,'qa_ndvi_slope3_total']=ndvi[j]-ndvi[j-2]
            pstart=max(0,j-5)
            # Existing v2 median includes 3..5 most recent prior observations,
            # even if a prior observation is too old or quality-rejected.
            histgood=(j>=3 and ok[pstart:j+1].all() and prev_gap_ok[pstart+1:j+1].all()
                      and np.isfinite(ndvi[pstart:j+1]).all())
            df.at[row_ix,'qa_window_prev5_ok']=bool(histgood)
            if histgood:
                df.at[row_ix,'qa_ndvi_dev_from_prev5_median']=ndvi[j]-np.median(ndvi[pstart:j])
    df=df.sort_values('_original_row_number').drop(columns=['_original_row_number','_quality_valid'])
    df['date']=df['date'].dt.strftime('%Y-%m-%d')
    return df


def build(base_path,v2_path,emit_zip,out):
    base_path=Path(base_path);v2_path=Path(v2_path);emit_zip=Path(emit_zip);out=Path(out)
    data_dir=out/'data';sources=out/'sources';audit_dir=out/'audit'
    for d in (data_dir,sources,audit_dir):d.mkdir(parents=True,exist_ok=True)
    a=pd.read_csv(base_path,low_memory=False); b=pd.read_csv(v2_path,low_memory=False)
    combined,retro,merge_audit=merge(a,b)
    # Safety checks before writing anything user-facing.
    assert len(a)==len(combined)==615 and combined.field_id.nunique()==20
    assert not combined.duplicated(KEYS).any()
    assert len(set(combined.date))==33
    assert not any(c.startswith('retro_') for c in combined.columns)
    assert not set(combined.columns)&{'true_damage_label','injected_class','simulated_class'}
    assert (combined.loc[:,a.columns].reset_index(drop=True).equals(a.reset_index(drop=True)) or
            all(pd.Series(combined[c]).equals(pd.Series(a[c])) for c in a.columns))

    # Canonical source untouched; write new derived datasets.
    combined_path=data_dir/'agrilens_real_field_date_enhanced_615.csv'
    retro_path=data_dir/'agrilens_retrospective_patterns_NOT_FOR_MODEL.csv'
    qa_path=data_dir/'agrilens_real_field_date_QA_gated_615.csv'
    combined.to_csv(combined_path,index=False)
    retro.to_csv(retro_path,index=False)
    qa=apply_qa_windows(combined)
    assert len(qa)==615 and not qa.duplicated(KEYS).any()
    qa.to_csv(qa_path,index=False)

    copy={'agrilens_original_screening_615.csv':base_path,
          'agrilens_v2_real_tidy_source_615.csv':v2_path}
    for name,src in copy.items():shutil.copy2(src,sources/name)
    with ZipFile(emit_zip) as z:
        assert z.testzip() is None
        names=z.namelist()
        wanted={
         'egypt_emit_s2_field_alignment.csv':'agrilens_EMIT_master_20_fields.csv',
         'egypt_hsi_s2_usable_fields.csv':'agrilens_EMIT_S2_usable_14_fields.csv',
         'egypt_hsi_complete_spectra.csv':'agrilens_EMIT_complete_spectra_3248.csv',
         'source_mask_verification.json':'EMIT_source_mask_verification.json',
         'selection_bias_by_split.csv':'EMIT_selection_bias_by_split.csv',
        }
        for name,dest in wanted.items():
            matches=[x for x in names if x.endswith('/'+name) or x==name]
            if len(matches)!=1: raise ValueError('Expected one archived file '+name+', found '+str(matches))
            loc=(audit_dir if dest.endswith('.json') or 'bias_' in dest else data_dir)/dest
            loc.write_bytes(z.read(matches[0]))
    # Copy existing manual review queue without recomputation.
    queue=base_path.parent/'manual_field_review_queue.csv'
    if queue.exists():shutil.copy2(queue,data_dir/'agrilens_manual_review_queue_196.csv')

    mf=pd.read_csv(data_dir/'agrilens_EMIT_master_20_fields.csv')
    uf=pd.read_csv(data_dir/'agrilens_EMIT_S2_usable_14_fields.csv')
    sp=pd.read_csv(data_dir/'agrilens_EMIT_complete_spectra_3248.csv')
    assert len(mf)==20 and len(uf)==14 and len(sp)==3248
    assert not sp.isna().any().any()
    assert set(uf.field_id).issubset(set(mf.field_id))
    assert len(qa.columns)==len(a.columns)+3+6
    # Verify exact preservation of source measurements/splits and no verified labels.
    for c in a.columns:
        if not qa[c].equals(a[c]):
            raise AssertionError('Original source column modified: '+c)
    if truth_values(qa.damage_label_verified).sum()!=0:
        raise AssertionError('Verified labels were unexpectedly present')
    per_split=(qa.groupby('field_split').agg(field_date_rows=('field_id','size'),unique_fields=('field_id','nunique'))
               .reset_index())
    per_split.to_csv(audit_dir/'geographic_split_counts.csv',index=False)
    feature_stats={c:{'nonmissing_rows':int(qa[c].notna().sum()),'missing_rows':int(qa[c].isna().sum())} for c in ADDED+QA_FEATURES}
    verification={
      'status':'PASS_REAL_OBSERVATIONS_ENRICHED_NO_SYNTHETIC_DATA',
      'row_unit':'One geographic field on one Sentinel-2 observation date',
      'existing_fields':20,'existing_field_date_rows':615,
      'unique_observation_dates':33,
      'source_base_columns':len(a.columns),
      'base_additive_columns':len(combined.columns),
      'QA_gated_columns':len(qa.columns),
      'new_v2_features':ADDED,
      'new_QA_gated_features':QA_FEATURES,
      'quality_assurance':'Require current/past valid observations and consecutive gaps <=15 days for QA features; CUSUM resets on gaps or invalid pairs.',
      'original_base_columns_exactly_preserved':True,
      'field_date_keys_and_split_preserved':True,
      'synthetic_records_joined':0,
      'independently_verified_dust_drought_damage_labels':0,
      'forecasting_or_dust_drought_classification_accuracy_claim':None,
      'dates_vs_pixel_dataset':'33 field-table dates; separate reported pixel-level 34 dates not reconciled here',
      'per_split':per_split.to_dict(orient='records'),
      'feature_nonmissing_counts':feature_stats,
      'EMIT':{'eligible_fields':len(mf),'usable_fields':len(uf),'complete_field_wavelength_rows':len(sp),
              'date':'2025-06-15','separate_one-date_layer':True},
      'input_source_sha256':{'original_manual_screening':sha256(base_path),'v2_real_tidy':sha256(v2_path),'frozen_EMIT_archive':sha256(emit_zip)},
      'limitations':[
       'Original dust, moisture, and meteorology measurements may be regional rather than field-specific.',
       'No causal dust-versus-drought crop-damage labels are present or inferred.',
       'Temporal pattern descriptors in NOT_FOR_MODEL table may use future dates.',
       'QA-gated features remain exploratory; negative CUSUM detects decline shapes, not causes.',
       'Six EMIT training fields remain masked; geographic selection bias is unresolved.',
       'EMIT spectral observations are single-date; never treat them as a 615-row HSI time series.',
      ]
    }
    (audit_dir/'verification_report.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    hashes=[]
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.name!='SHA256_manifest.csv':
            hashes.append({'relative_file':p.relative_to(out).as_posix(),'SHA256':sha256(p),'bytes':p.stat().st_size})
    with (out/'SHA256_manifest.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['relative_file','SHA256','bytes']);writer.writeheader();writer.writerows(hashes)
    return verification

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True);parser.add_argument('--v2',required=True)
    parser.add_argument('--emit-zip',required=True);parser.add_argument('--out',required=True)
    x=parser.parse_args()
    print(json.dumps(build(x.base,x.v2,x.emit_zip,x.out),indent=2))
