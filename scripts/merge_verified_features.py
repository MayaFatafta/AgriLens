#!/usr/bin/env python3
"""Safe additive-only AgriLens field-date feature enrichment.

Preserves the authoritative real dataset and joins only 3 past/present-derived
features from v2.  Future-dependent retrospective information is exported to a
SEPARATE, explicitly non-operational table.  Never merges synthetic benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

KEYS = ["field_id", "date"]
EXTRA_CAUSAL = ["ndvi_slope3_total", "ndvi_dev_from_prev5_median", "cusum_neg"]
RETRO = ["retro_next_delta_ndvi", "retro_temporal_pattern"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda:f.read(1<<20), b''):
            h.update(block)
    return h.hexdigest()


def _check_keys(df, label):
    miss = [c for c in KEYS+["field_split"] if c not in df.columns]
    if miss: raise ValueError(f'{label}: missing {miss}')
    if df[KEYS].isna().any().any(): raise ValueError(f'{label}: missing field/date key')
    if df.duplicated(KEYS).any(): raise ValueError(f'{label}: duplicate field-date keys')
    if set(df.field_split.unique()) - {'train','validation','test'}:
        raise ValueError(f'{label}: invalid audited split')


def _normalized(df):
    df=df.copy()
    df['date']=pd.to_datetime(df['date'],errors='raise').dt.strftime('%Y-%m-%d')
    df['field_id']=pd.to_numeric(df['field_id'], errors='raise').astype('int64')
    return df


def _equal_series(x,y):
    if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
        return bool(np.isclose(x.to_numpy(dtype=float),y.to_numpy(dtype=float),
                               equal_nan=True,rtol=1e-10,atol=1e-12).all())
    return bool(x.fillna('<NULL>').astype(str).equals(y.fillna('<NULL>').astype(str)))


def merge(base, extra):
    """Return new enhanced real dataset, separate retrospective annotations, audit."""
    a=_normalized(base); b=_normalized(extra)
    _check_keys(a,'authoritative base');_check_keys(b,'v2-derived data')
    missing=[c for c in EXTRA_CAUSAL+RETRO+['label_verified','quality_ok','pair_ok'] if c not in b.columns]
    if missing: raise ValueError(f'v2 missing mandatory columns: {missing}')
    if not (b['label_verified'].fillna(False).eq(False)).all():
        raise ValueError('v2 unexpectedly claims verified labels')
    ak=set(map(tuple,a[KEYS].itertuples(index=False,name=None)))
    bk=set(map(tuple,b[KEYS].itertuples(index=False,name=None)))
    if ak != bk:
        raise ValueError(f'Field-date keys differ: base_only={len(ak-bk)}, v2_only={len(bk-ak)}')
    aa=a.set_index(KEYS).sort_index();bb=b.set_index(KEYS).sort_index()
    shared=sorted(set(aa.columns)&set(bb.columns))
    inconsistent=[c for c in shared if not _equal_series(aa[c],bb[c])]
    if inconsistent: raise ValueError('Shared columns differ: '+', '.join(inconsistent))
    overlapping=set(EXTRA_CAUSAL)&set(a.columns)
    if overlapping: raise ValueError('Existing feature would be overwritten: '+str(overlapping))
    operational=b[KEYS+EXTRA_CAUSAL+['quality_ok','pair_ok']].copy()
    operational=operational.rename(columns={x:'v2_'+x for x in EXTRA_CAUSAL})
    # Qualify imported numeric features; they are not ground truth or dust labels.
    for c in ['v2_'+x for x in EXTRA_CAUSAL]:
        operational.loc[~operational.quality_ok.astype(bool),c]=np.nan
    operational=operational.drop(columns=['quality_ok','pair_ok'])
    joined=a.merge(operational,on=KEYS,how='left',validate='one_to_one',sort=False)
    if len(joined) != len(a):raise AssertionError('Source row count changed')
    retros=b[KEYS+['field_split']+RETRO].copy()
    retros['record_kind']='RETROSPECTIVE_TEMPORAL_PATTERN_NOT_DUST_OR_DROUGHT_DIAGNOSIS'
    retros['verified_damage_label']=False
    audit={
      'status':'ADDITIVE_REAL_DATA_FEATURE_ENHANCEMENT_NO_NEW_OBSERVATIONS',
      'master_data_unchanged':True,'same_field_date_keys':True,
      'rows_before':len(a),'rows_after':len(joined),'unique_fields':int(a.field_id.nunique()),
      'shared_columns_verified_identical':len(shared),
      'geographic_split_preserved':True,'new_operational_columns':['v2_'+c for c in EXTRA_CAUSAL],
      'retrospective_columns_in_separate_file':RETRO,
      'synthetic_rows_joined':0,'independently_verified_damage_labels_added':0,
      'feature_derivation':'v2 past/current observation indices; one-sided CUSUM, 3-observation difference, trailing 5-observation median',
      'cautions':['Quality-failed current rows have new feature values set to missing; past poor-quality observations can still affect v2 trailing-window features and should be rechecked before predictive use.',
                  'Retrospective patterns use future observations and must NOT be model inputs.',
                  'Regional atmospheric/soil-moisture context is not field-specific exposure.',
                  'No new independent observations, dust/drought labels, or geographic coverage.'],
      'per_split':joined.groupby('field_split').agg(rows=('field_id','size'),fields=('field_id','nunique')).to_dict(orient='index')
    }
    return joined,retros,audit


def run(base_path, v2_path, output):
    base_path=Path(base_path);v2_path=Path(v2_path);output=Path(output)
    a=pd.read_csv(base_path,low_memory=False);b=pd.read_csv(v2_path,low_memory=False)
    joined,retro,audit=merge(a,b)
    output.mkdir(parents=True,exist_ok=True)
    audit['input_sha256']={base_path.name:sha256(base_path),v2_path.name:sha256(v2_path)}
    files={'enhanced_real_field_date_screening.csv':joined,
           'retrospective_temporal_patterns_NOT_FOR_MODEL.csv':retro}
    for name,df in files.items():df.to_csv(output/name,index=False)
    audit['output_sha256']={name:sha256(output/name) for name in files}
    (output/'enhancement_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps({k:audit[k] for k in ['status','rows_before','rows_after','unique_fields','shared_columns_verified_identical','new_operational_columns','synthetic_rows_joined','independently_verified_damage_labels_added']},indent=2))
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',required=True,help='Original 615-row manual screening CSV')
    p.add_argument('--v2',required=True,help='Real-only v2 tidy field-date CSV')
    p.add_argument('--out',required=True,help='NEW output directory, never original frozen release')
    x=p.parse_args();run(x.base,x.v2,x.out)
