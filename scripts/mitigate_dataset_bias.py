#!/usr/bin/env python3
"""AgriLens field-level selection and preprocessing audit.

No unverified crop-damage labels are created or inferred. The quality-screened
Egyptian EMIT/Sentinel-2 data remain observational and exploratory.
Requires pandas and numpy only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_SPLITS = ('train', 'validation', 'test')
KEYS = ['field_id', 'wavelength_nm']
TARGETS_NM = {'r665': 665., 'r705': 705., 'r750': 750., 'r860': 860., 'r1650': 1650., 'r2200': 2200.}


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),''):
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_master(master:pd.DataFrame):
    needed={'field_id','field_split','emit_valid_pixel_count','emit_field_pixel_centers_total',
            'emit_quality_coverage_fraction','s2_ndvi_mean','emit_ndvi_median','s2_split_recorded',
            'emit_acquired_utc','s2_observation_date','s2_minus_emit_days'}
    require(needed.issubset(master.columns),f'Missing master columns: {needed-set(master.columns)}')
    require(not master.field_id.duplicated().any(), 'Duplicate master field IDs')
    require(master.field_split.isin(EXPECTED_SPLITS).all(), 'Unexpected geographic split labels')
    require((master.emit_valid_pixel_count>=0).all(),'Negative pixel counts')
    require((master.emit_field_pixel_centers_total>=master.emit_valid_pixel_count).all(), 'More valid than total field pixels')
    require(master.emit_quality_coverage_fraction.between(0,1).all(), 'Coverage outside [0,1]')
    require(np.allclose(master.emit_quality_coverage_fraction,
        np.where(master.emit_field_pixel_centers_total>0,
                 master.emit_valid_pixel_count/master.emit_field_pixel_centers_total,0),atol=1e-6),
            'Coverage inconsistent with pixel counts')
    require(master.loc[master.emit_valid_pixel_count.eq(0),'emit_ndvi_median'].isna().all(),
            'Zero-EMIT fields unexpectedly have reflectance-derived NDVI')
    require(master.loc[master.emit_valid_pixel_count.gt(0),'emit_ndvi_median'].notna().all(),
            'Positive-EMIT fields have missing NDVI')
    require(master.s2_ndvi_mean.between(-1,1).all(), 'Invalid S2 NDVI')
    require(master.loc[master.emit_ndvi_median.notna(),'emit_ndvi_median'].between(-1,1).all(), 'Invalid EMIT NDVI')


def check_spectra(spectra:pd.DataFrame, usable:pd.DataFrame):
    needed={'field_id','wavelength_nm','reflectance_median','n_valid_spectral_samples','field_pixel_count','emit_acquisition_date'}
    require(needed.issubset(spectra.columns),f'Missing spectral columns: {needed-set(spectra.columns)}')
    require(not spectra.duplicated(KEYS).any(), 'Duplicate field-wavelength records')
    require(spectra.reflectance_median.notna().all(), 'NaNs in complete spectra')
    require(np.isfinite(spectra.reflectance_median).all(), 'Nonfinite reflectance')
    require(spectra.reflectance_median.between(0,1.2).all(), 'Out-of-range reflectance; investigate source calibration')
    require(set(spectra.field_id)==set(usable.field_id), 'Different field sets in tables')
    n_fields=usable.field_id.nunique()
    bands=spectra.wavelength_nm.nunique()
    require(len(spectra)==n_fields*bands, 'Incomplete rectangular field x wavelength table')
    require(spectra.groupby('field_id').wavelength_nm.nunique().eq(bands).all(), 'Different bands per field')
    require(spectra.n_valid_spectral_samples.ge(1).all(), 'Zero spectra sample counts')
    validmap=usable.set_index('field_id').emit_valid_pixel_count
    require(spectra.apply(lambda x:x.n_valid_spectral_samples <= validmap.loc[x.field_id],axis=1).all(),
            'Spectral sample count exceeds field valid pixel count')


def select_bands(spectra):
    w=np.sort(spectra.wavelength_nm.unique())
    selected={}
    for k, target in TARGETS_NM.items():
        idx=int(np.argmin(np.abs(w-target)))
        chosen=float(w[idx]);require(abs(chosen-target)<=15, f'No retained spectral wavelength near {target}')
        selected[k]=chosen
    return selected


def create_features(master, usable, spectra):
    chosen=select_bands(spectra)
    f=usable.copy()
    for key,band in chosen.items():
        col=spectra.loc[spectra.wavelength_nm==band,['field_id','reflectance_median']].rename(
            columns={'reflectance_median':key})
        f=f.merge(col,on='field_id',how='left',validate='one_to_one')
    f['red_edge_slope_705_750']=(f.r750-f.r705)/(chosen['r750']-chosen['r705'])
    f['nir_to_red_reflectance_ratio']=(f.r860/(f.r665.replace(0,np.nan)))
    f['swir_1650_minus_2200']=f.r1650-f.r2200
    f['emit_coverage_under_50pct']=f.emit_quality_coverage_fraction.lt(.50)
    f['source_quality_adequacy']=f.emit_valid_pixel_count.ge(3)
    cols=['emit_ndvi_median','emit_ndre_median','emit_ndmi_median','r665','r705','r750','r860','r1650','r2200',
          'red_edge_slope_705_750','nir_to_red_reflectance_ratio','swir_1650_minus_2200']
    require(f[cols].notna().all().all(), 'Engineered features have missing entries')
    require(np.isfinite(f[cols].to_numpy(dtype=float)).all(), 'Nonfinite engineered feature')
    # Deliberately exclude environmental columns. They are constant on this one date.
    for c in ['s2_date_dust','s2_date_aerosol_optical_depth','s2_date_soil_moisture_28_to_100cm','s2_date_precip_48h']:
        if c in f:
            require(np.allclose(f[c].to_numpy(dtype=float),f[c].iloc[0],atol=1e-12,rtol=0),
                    f'Unexpected spatial variance in {c}; review date alignment')
    return f,cols,chosen


def train_only_scaler(data, columns):
    """Compute transformation only on the existing geographic TRAIN fields.

    No label-dependent feature selection. This is a demonstration only because
    there are only 3 training fields.
    """
    tr=data[data.field_split=='train']
    require(len(tr)>=2,'Cannot fit scaling on fewer than two training fields')
    require(data.field_id.is_unique,'Field IDs not unique')
    mean=tr[columns].mean()
    std=tr[columns].std(ddof=0)
    z=data[['field_id','field_split','emit_acquired_utc','s2_observation_date']].copy()
    zero=[]
    for c in columns:
        if float(std[c])<1e-12:
            zero.append(c)
            z[c+'_scaled']=0.0
        else:
            z[c+'_scaled']=(data[c]-mean[c])/std[c]
    p={c:{'train_mean':float(mean[c]),'train_std_population':float(std[c]),
           'is_constant_in_training':c in zero} for c in columns}
    require(np.isfinite(z.filter(like='_scaled').to_numpy(dtype=float)).all(),'Nonfinite scaled feature')
    return z,p,zero


def build_review_queue(master):
    q=master[['field_id','field_split','emit_valid_pixel_count','emit_quality_coverage_fraction',
              's2_observation_date','s2_ndvi_mean']].copy()
    q['no_valid_emit_pixels']=q.emit_valid_pixel_count.eq(0)
    q['low_emit_coverage_lt50pct']=q.emit_quality_coverage_fraction.lt(.5)
    q['priority']=np.where(q.no_valid_emit_pixels, 'P1_missing_EMIT',
                           np.where(q.low_emit_coverage_lt50pct,'P2_low_coverage','P3_document_reference'))
    q['recommended_action']=np.where(q.no_valid_emit_pixels, 'Seek additional same-AOI genuine acquisition and check masks',
                                    np.where(q.low_emit_coverage_lt50pct,'Obtain repeated clear observation; retain QA flag',
                                             'Obtain independent crop/irrigation/soil observation if possible'))
    return q.sort_values(['priority','field_split','field_id'])


def run(input_dir, out_dir):
    input_dir=Path(input_dir);out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    master_p=input_dir/'egypt_emit_s2_field_alignment.csv'
    usable_p=input_dir/'egypt_hsi_s2_usable_fields.csv'
    spectra_p=input_dir/'egypt_hsi_complete_spectra.csv'
    rawspec_p=input_dir/'egypt_emit_field_spectra.csv'
    for p in [master_p,usable_p,spectra_p,rawspec_p]:require(p.is_file(),f'Missing file: {p}')
    master=pd.read_csv(master_p); usable=pd.read_csv(usable_p);spec=pd.read_csv(spectra_p);raw=pd.read_csv(rawspec_p)
    check_master(master);check_spectra(spec,usable)
    require(set(usable.field_id)==set(master.loc[master.emit_valid_pixel_count.ge(3),'field_id']),
            'Usable field set is inconsistent with master QA table')
    require(not raw.duplicated(KEYS).any(), 'Duplicated original spectra rows')
    missing_waves=raw.groupby('wavelength_nm',as_index=False).agg(n_field_rows=('field_id','size'),
                                                                   n_missing=('reflectance_median',lambda z:int(z.isna().sum())))
    missing_waves=missing_waves[missing_waves.n_missing.gt(0)].sort_values('wavelength_nm')
    f,cols,selected=create_features(master,usable,spec)
    z,scale_params,train_zero=train_only_scaler(f,cols)
    field_master=master.copy()
    field_master['has_usable_emit']=field_master.field_id.isin(usable.field_id)
    field_master['low_quality_coverage_lt50pct']=field_master.emit_quality_coverage_fraction.lt(.5)
    field_master['historical_split_disagrees']=field_master.field_split.ne(field_master.s2_split_recorded)
    field_master['availability_reason']=np.where(field_master.has_usable_emit,'usable_emitspectra', 'no_quality_valid_emit_pixels')
    # Preserve NaNs in source columns; do not impute missing satellite observations.
    field_master.to_csv(out_dir/'master_20_fields_with_availability.csv',index=False)
    f.to_csv(out_dir/'exploratory_14_field_features.csv',index=False)
    z.to_csv(out_dir/'demonstration_train_fitted_scaled_features.csv',index=False)
    spec.to_csv(out_dir/'complete_232_wavelength_spectra.csv',index=False)
    missing_waves.to_csv(out_dir/'excluded_missing_wavelengths.csv',index=False)
    review=build_review_queue(master);review.to_csv(out_dir/'prioritized_evidence_collection.csv',index=False)
    anno=review[['field_id','field_split','s2_observation_date']].copy()
    anno['target_definition']='cause_of_observed_crop_stress'
    anno['verified_label']='unverified'
    anno['independent_evidence_type']=''
    anno['independent_evidence_reference']=''
    anno['field_observation_date']=''
    anno['reviewer']=''
    anno['confidence']=''
    anno['annotation_notes']=''
    anno['adjudicator']=''
    anno['adjudication_status']='not_reviewed'
    anno.to_csv(out_dir/'independent_annotation_template.csv',index=False)
    by_split=field_master.groupby('field_split').agg(eligible_fields=('field_id','count'),
                             usable_emit_fields=('has_usable_emit','sum'),
                             mean_coverage=('emit_quality_coverage_fraction','mean')).reset_index()
    by_split['retention_fraction']=(by_split.usable_emit_fields/by_split.eligible_fields)
    by_split.to_csv(out_dir/'selection_bias_by_split.csv',index=False)
    with open(out_dir/'train_only_scaler_parameters.json','w') as fp:
        json.dump({'warning':'DEMONSTRATION ONLY: 3 train fields, NOT a validated predictive model.',
                   'fit_split':'train','n_training_fields':int((f.field_split=='train').sum()),
                   'features_used':cols,'parameters':scale_params,'training_constant_features':train_zero,
                   'bands_used_nm':selected}, fp,indent=2)
    flagged=f.loc[f.emit_coverage_under_50pct,['field_id','field_split','emit_valid_pixel_count','emit_quality_coverage_fraction']]
    warnings=[]
    if (f.field_split=='train').sum()<10:warnings.append('Only 3 training fields; do not train a generalizable HSI classifier.')
    if not flagged.empty:warnings.append('Low coverage remains; do not drop these fields silently.')
    warnings+=['No independently verified dust/drought injury labels; class balance and supervised metrics unavailable.',
               'Only one EMIT acquisition: hyperspectral seasonal generalization not demonstrated.',
               'All environmental variables constant by field on this comparison date.',
               'Missing EMIT data concentrated in training: selection bias remains.',
               'Date offset, 60m/20m resolution and field-median vs field-mean summaries prevent direct sensor-accuracy claims.']
    report={'project':'AgriLens','phase':'mitigated_exploratory_dataset_NOT_supervised_classifier',
            'source_sha256':{p.name:sha256(p) for p in [master_p,usable_p,spectra_p,rawspec_p]},
            'structure':{'master_fields':len(master),'usable_fields':len(usable),'complete_spectral_bands':spec.wavelength_nm.nunique(),
                         'spectral_field_band_rows':len(spec),'spectral_duplicate_pairs':int(spec.duplicated(KEYS).sum()),
                         'spectral_missing_reflectance_values':int(spec.reflectance_median.isna().sum()),
                         'spectral_reflectance_min':float(spec.reflectance_median.min()),
                         'spectral_reflectance_max':float(spec.reflectance_median.max()),
                         'original_missing_spectra_rows':int(raw.reflectance_median.isna().sum()),
                         'excluded_missing_wavelength_count':len(missing_waves),
                         'all_fields_having_unique_id':bool(master.field_id.is_unique)},
            'bias':{'train_val_test_retention':by_split.to_dict('records'),
                    'fields_missing_emit_ids':master.loc[master.emit_valid_pixel_count.eq(0),'field_id'].astype(int).tolist(),
                    'low_coverage_under_50pct_fields':flagged.to_dict('records'),
                    'split_conflict_count_all_20':int(field_master.historical_split_disagrees.sum()),
                    'split_conflict_count_usable_14':int(f.field_split.ne(f.s2_split_recorded).sum()),
                    'authoritative_split':'field_split',
                    'ndvi_field_equal_mean':float(f.emit_ndvi_median.mean()),
                    'ndvi_pixel_weighted_mean':float(np.average(f.emit_ndvi_median, weights=f.emit_valid_pixel_count)),
                    'single_date_environmental_features_excluded_from_model_vectors':
                    [x for x in ['s2_date_dust','s2_date_aerosol_optical_depth','s2_date_soil_moisture_28_to_100cm','s2_date_precip_48h'] if x in f.columns]},
            'feature_engineering':{'selected_bands_nm':selected,'features':cols,
                                  'training_fields_used_for_scaling':int((f.field_split=='train').sum()),
                                  'train_variance_zero_features':train_zero,
                                  'scaler_learned_from_validation_or_test':False},
            'labeling':{'verified_dust_drought_stress_labels':0,'unverified_annotation_count':len(anno),
                        'class_counts':None,'can_assess_class_balance':False,
                        'can_report_supervised_accuracy':False},
            'acceptance':{'descriptive_same_AOI_monitoring':'PASS_WITH_CAVEATS',
                          'train_only_feature_scaling_implementation':'PASS_TECHNICAL_ONLY',
                          'satellite_coverage_representativeness':'FAIL',
                          'independent_dust_drought_labels':'FAIL',
                          'supervised_hsi_classifier_readiness':'FAIL'},
            'warnings':warnings}
    with open(out_dir/'mitigation_verification_report.json','w') as fp:json.dump(report,fp,indent=2)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input-dir',default='inputs')
    p.add_argument('--out',default='outputs')
    args=p.parse_args();r=run(args.input_dir,args.out)
    print(json.dumps({'status':r['phase'],'fields':r['structure']['usable_fields'],
     'spectral_bands':r['structure']['complete_spectral_bands'],'splits':r['bias']['train_val_test_retention'],
     'verified_labels':r['labeling']['verified_dust_drought_stress_labels'],
     'acceptance':r['acceptance']},indent=2))
if __name__=='__main__':main()
