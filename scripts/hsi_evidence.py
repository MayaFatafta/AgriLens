"""AgriLens Tanager spectral-information evaluation.

This does NOT evaluate crop stress, causal attribution, or genuine Sentinel-2 imagery.
It compares Tanager spectra against a sparse SAME-SCENE band-center approximation.

Aggregate mode: use user-provided Tanager-derived median signatures (runs offline).
Pixel mode: use original real Tanager HDF5 to quantify approximation error per pixel.
Source mode: log local SHA-256 and metadata consistency; not external checksum auth.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OFFICIAL_SCENE_ID = '20250501_143138_87_4001'
OFFICIAL_SOURCE_URL = ('https://storage.googleapis.com/open-cogs/planet-stac/'
    'tanager1-release2-core-imagery/ortho_sr_hdf5/'
    '20250501_143138_87_4001_ortho_sr_hdf5.h5')
SOURCE_DOC = 'https://planetlabs.github.io/tanager-opendata-edu/module-4/spectral-indices-p2/'
SR_PATH = 'HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance'
BASE = 'HDFEOS/GRIDS/HYP/Data Fields'
ANCHOR_CENTERS_NM = (665,705,740,783,842,865)  # center-only approximation; NOT sensor SRFs
TARGET_RANGE_NM = (680,800)


def nearest_bands(wavelengths: np.ndarray, centers=ANCHOR_CENTERS_NM) -> np.ndarray:
    w=np.asarray(wavelengths,dtype=float)
    indices=np.array([int(np.argmin(np.abs(w-c))) for c in centers])
    if np.any(np.abs(w[indices]-np.asarray(centers))>12):
        raise ValueError('Input wavelengths cannot approximate requested centers within 12 nm')
    if np.unique(indices).size!=len(indices):
        raise ValueError('Different center wavelengths mapped to the same band')
    return indices


def errors_for_curves(wavelengths, curves, target_range=TARGET_RANGE_NM):
    """Observed dense spectra vs linear interpolation through selected same-scene centers."""
    wavelengths=np.asarray(wavelengths,float)
    curves=np.asarray(curves,float)
    if curves.ndim==1: curves=curves[None,:]
    if curves.shape[-1]!=len(wavelengths): raise ValueError('Wavelength/spectrum shape mismatch')
    inds=nearest_bands(wavelengths)
    in_window=(wavelengths>=target_range[0]) & (wavelengths<=target_range[1])
    if np.count_nonzero(in_window)<8: raise ValueError('Too few red-edge wavelengths')
    x=wavelengths[in_window]
    approx=np.stack([np.interp(x,wavelengths[inds],row[inds]) for row in curves])
    truth=curves[:,in_window]
    if not np.all(np.isfinite(approx)) or not np.all(np.isfinite(truth)):
        raise ValueError('Nonfinite red-edge observations or band-center samples')
    residual=truth-approx
    per_curve_rmse=np.sqrt(np.mean(residual**2,axis=1))
    return {'centers_observed_nm':wavelengths[inds], 'window_wavelengths_nm':x,
            'observed':truth,'approximation':approx,'residual':residual,
            'rmse':per_curve_rmse, 'mae':np.mean(np.abs(residual),axis=1),
            'max_abs_error':np.max(np.abs(residual),axis=1)}


def _json_default(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    raise TypeError(str(type(x)))


def analyze_aggregates(csv_path:Path, report_path:Path, out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    src=pd.read_csv(csv_path)
    original_count=len(src)
    required=['wavelength_nm','median_reflectance_high_ndvi','median_reflectance_low_ndvi']
    if any(c not in src.columns for c in required): raise ValueError('Wrong signature CSV columns')
    bad=src[src[required].isna().any(axis=1)].copy()
    clean=src.dropna(subset=required).sort_values('wavelength_nm').reset_index(drop=True)
    if clean['wavelength_nm'].duplicated().any(): raise ValueError('Duplicate wavelengths')
    clean.to_csv(out/'spectral_signatures_clean.csv',index=False)
    bad.to_csv(out/'excluded_missing_wavelengths.csv',index=False)
    w=clean.wavelength_nm.to_numpy()
    actual=np.stack([clean[required[1]].to_numpy(),clean[required[2]].to_numpy()])
    experiment=errors_for_curves(w,actual)
    r=json.loads(report_path.read_text(encoding='utf-8'))
    agg={'evaluation':'descriptive spectral-shape information loss (NOT downstream predictive improvement)',
         'source_kind':'Tanager-derived group median spectra supplied by user',
         'source_authentication':r.get('status','unknown'),
         'original_scene_name_in_report':r.get('scene_id'),
         'candidate_scene_id_from_official_tutorial':OFFICIAL_SCENE_ID,
         'reference_url':OFFICIAL_SOURCE_URL,
         'n_original_spectral_rows':original_count,'n_clean_spectral_rows':len(clean),
         'excluded_wavelengths_nm':bad.wavelength_nm.tolist(),
         'group_labels':['higher_NDVI_quantile','lower_NDVI_quantile'],
         'group_membership_is_NDVI_based':True,
         'n_sampled_pixels_per_group':r.get('spectral_processing',{}).get('sampled_pixel_counts',{}),
         'spectral_window_nm':[680,800],
         'center_approximations_nm':ANCHOR_CENTERS_NM,
         'actual_sampled_band_centers_nm':experiment['centers_observed_nm'],
         'rededge_rmse_reflectance':dict(zip(['higher_NDVI_quantile','lower_NDVI_quantile'],experiment['rmse'])),
         'rededge_mae_reflectance':dict(zip(['higher_NDVI_quantile','lower_NDVI_quantile'],experiment['mae'])),
         'rededge_max_abs_error_reflectance':dict(zip(['higher_NDVI_quantile','lower_NDVI_quantile'],experiment['max_abs_error'])),
         'limitations':[
            'Not a real Sentinel-2 sensor simulation (no spectral response convolution).',
            'Comparison uses TWO median spectra, not per-pixel distributions.',
            'Groups defined using NDVI are not independent crop condition labels.',
            'No independent measurements of crop stress, disease, soil moisture or yield.',
            'No observation from Satellite 813 was processed.',
            'Scene over Brazil is geographically separate from Egyptian time series.',
         ]}
    (out/'aggregate_spectral_evidence.json').write_text(json.dumps(agg,indent=2,default=_json_default),encoding='utf-8')
    labels=['Higher NDVI quantile','Lower NDVI quantile']
    fig,axes=plt.subplots(2,1,figsize=(11,8),sharex=True,layout='constrained')
    for j,label in enumerate(labels):
        axes[0].plot(experiment['window_wavelengths_nm'],experiment['observed'][j],lw=2,label=f'{label}: measured narrow bands')
        axes[0].plot(experiment['window_wavelengths_nm'],experiment['approximation'][j],ls='--',lw=1.7,label=f'{label}: sparse-center interpolation')
        axes[1].plot(experiment['window_wavelengths_nm'],experiment['residual'][j],lw=1.4,label=f'{label} residual')
    for c in experiment['centers_observed_nm']:
        if 680<=c<=800: axes[0].axvline(c,alpha=.17,color='gray')
    axes[0].set_ylabel('Median surface reflectance')
    axes[0].set_title('Real Tanager-derived median spectra vs center-sampled approximation (680–800 nm)')
    axes[0].grid(alpha=.2); axes[0].legend(fontsize=8,ncol=2)
    axes[1].axhline(0,color='black',lw=.8); axes[1].grid(alpha=.2)
    axes[1].set_ylabel('Measured − interpolated reflectance')
    axes[1].set_xlabel('Wavelength (nm)');axes[1].legend(fontsize=8)
    fig.suptitle('Spectral detail diagnostic · not a crop-stress accuracy comparison',fontsize=12)
    fig.savefig(out/'rededge_sparse_vs_dense.png',dpi=170)
    plt.close(fig)
    return agg


def read_wavelengths_from_hdf(f):
    sr=f[SR_PATH]
    objects=[sr,sr.parent,f.get('HDFEOS/GRIDS/HYP'),f]
    for o in objects:
        if o is None: continue
        for name in ('wavelengths','wavelength','Wavelengths','band_centers','central_wavelengths'):
            if name in o.attrs:
                w=np.asarray(o.attrs[name],dtype=float).ravel()
                if len(w)==sr.shape[0]:
                    if np.nanmax(w)<20: w=w*1000
                    if not np.all(np.diff(w)>0): raise ValueError('Wavelengths not strictly increasing')
                    return w
    for p in (f'{BASE}/wavelengths','HDFEOS/GRIDS/HYP/wavelengths'):
        if p in f:
            w=np.asarray(f[p][...],dtype=float).ravel()
            if len(w)==sr.shape[0]:
                if np.nanmax(w)<20: w=w*1000
                return w
    raise ValueError('Wavelengths not in HDF5; matching official scene metadata required')


def _sample_band(sr,idx,stride):
    return np.asarray(sr[idx,::stride,::stride],dtype=np.float32).reshape(-1)


def pixelwise_experiment(h5_path:Path,out:Path,stride:int=8,max_pixels:int=1500,min_ndvi:float=.3)->dict:
    if stride<1 or max_pixels<10: raise ValueError('Use stride>=1 and max_pixels>=10')
    out.mkdir(parents=True,exist_ok=True)
    with h5py.File(h5_path,'r') as f:
        if SR_PATH not in f: raise ValueError('Input is not Tanager ortho surface reflectance HDF5')
        sr=f[SR_PATH]
        wl=read_wavelengths_from_hdf(f)
        anchor=nearest_bands(wl)
        d_idx=np.flatnonzero((wl>=680)&(wl<=800))
        if len(d_idx)<8: raise ValueError('Insufficient dense red-edge sampling')
        nir_idx=int(np.argmin(np.abs(wl-860)))
        red_idx=int(np.argmin(np.abs(wl-665)))
        need=np.unique(np.r_[anchor,d_idx,nir_idx,red_idx])
        y_shape,x_shape=sr.shape[1:]
        ys=np.arange(0,y_shape,stride)
        xs=np.arange(0,x_shape,stride)
        grid_size=len(ys)*len(xs)
        valid=np.ones(grid_size,dtype=bool)
        for mask_name in ('beta_cloud_mask','beta_cirrus_mask','nodata_pixels'):
            maskpath=f'{BASE}/{mask_name}'
            if maskpath not in f: raise ValueError(f'Missing quality mask {maskpath}')
            m=np.asarray(f[maskpath][::stride,::stride]).reshape(-1)
            valid&=(m==0)
        arrays={int(i):_sample_band(sr,int(i),stride) for i in need}
        for a in arrays.values(): valid &= np.isfinite(a)&(a>=0)&(a<=1.2)
        ndvi=(arrays[nir_idx]-arrays[red_idx])/(arrays[nir_idx]+arrays[red_idx]+1e-12)
        valid&=(ndvi>=min_ndvi)
        pool=np.flatnonzero(valid)
        if len(pool)<10: raise ValueError(f'Too few quality-screened vegetation samples: {len(pool)}')
        rng=np.random.default_rng(813)
        chosen=np.sort(rng.choice(pool,size=min(max_pixels,len(pool)),replace=False))
        sampled_wls=wl[np.sort(need)]
        dense=np.stack([arrays[int(i)][chosen] for i in d_idx],axis=1)
        sparse=np.stack([arrays[int(i)][chosen] for i in anchor],axis=1)
        approx=np.stack([np.interp(wl[d_idx],wl[anchor],s) for s in sparse])
        residual=dense-approx
        rmse=np.sqrt(np.mean(residual*residual,axis=1))
        mae=np.mean(np.abs(residual),axis=1)
        columns=len(xs)
        rr=ys[chosen//columns];cc=xs[chosen%columns]
        output=pd.DataFrame({'pixel_row':rr.astype(int),'pixel_col':cc.astype(int),'ndvi':ndvi[chosen],
                             'rededge_reconstruction_rmse':rmse,'rededge_reconstruction_mae':mae})
        output.to_csv(out/'pixelwise_sparse_band_errors.csv',index=False)
        stat={'evaluation':'per-pixel spectral-shape error of same-scene sparse-center approximation',
              'source':'local HDF5; scene source still requires independently verified scene/asset identity',
              'hdf5_path':str(h5_path),'cube_shape':list(sr.shape),'wavelength_range_nm':[float(wl.min()),float(wl.max())],
              'n_scene_pixels':int(y_shape*x_shape),'n_grid_points':int(grid_size),
              'n_quality_screened_vegetation_candidates':int(len(pool)),
              'n_sampled_pixels':int(len(chosen)),'stride':stride,'min_ndvi':min_ndvi,
              'rededge_wavelength_count':int(len(d_idx)),
              'rededge_window_nm':list(TARGET_RANGE_NM),
              'approximated_band_centers_nm':wl[anchor].tolist(),
              'rmse_reflectance_median':float(np.median(rmse)),
              'rmse_reflectance_mean':float(np.mean(rmse)),
              'rmse_reflectance_p05':float(np.percentile(rmse,5)),
              'rmse_reflectance_p95':float(np.percentile(rmse,95)),
              'note':'This is not Sentinel-2 sensor simulation and NOT validation of crop condition.'}
        (out/'pixelwise_spectral_evidence.json').write_text(json.dumps(stat,indent=2),encoding='utf-8')
        fig,ax=plt.subplots(1,2,figsize=(10,4),layout='constrained')
        ax[0].hist(rmse,bins=30);ax[0].set_xlabel('Reflectance RMSE per pixel');ax[0].set_ylabel('Sampled pixels')
        ax[0].set_title('Sparse-center reconstruction residual')
        mid_idx=int(np.argsort(rmse)[len(rmse)//2]);
        ax[1].plot(wl[d_idx],dense[mid_idx],label='Measured narrow-band reflectance')
        ax[1].plot(wl[d_idx],approx[mid_idx],linestyle='--',label='Center interpolation')
        ax[1].set_title('Example near median reconstruction error');ax[1].set_xlabel('Wavelength (nm)')
        ax[1].set_ylabel('Surface reflectance');ax[1].legend(fontsize=8)
        fig.suptitle('Tanager representation study, not crop-stress diagnostic accuracy')
        fig.savefig(out/'pixelwise_spectral_reconstruction.png',dpi=170)
        plt.close(fig)
        return stat


def verify_local_file(h5_path:Path,report_path:Path,out:Path,compute_hash:bool=True)->dict:
    """Local file consistency and fingerprint; only trusted publisher hash authenticates bytes."""
    report=json.loads(report_path.read_text(encoding='utf-8'))
    with h5py.File(h5_path,'r') as f:
        if SR_PATH not in f: raise ValueError('HDF5 lacks expected surface reflectance dataset')
        shape=list(f[SR_PATH].shape)
        wl=read_wavelengths_from_hdf(f)
        grid=f.get('HDFEOS/GRIDS/HYP')
        epsg=grid.attrs.get('epsg_code') if grid is not None else None
        if isinstance(epsg,bytes): epsg=epsg.decode(errors='replace')
        epsg=str(epsg) if epsg is not None else None
    expected=report['hdf5_metadata']; size=h5_path.stat().st_size
    results={'file_path':str(h5_path.resolve()),'bytes':size,'cube_shape':shape,
             'epsg':epsg,'wavelength_nm_minmax':[float(wl[0]),float(wl[-1])],
             'matches_uploaded_report_size':size==expected['bytes'],
             'matches_uploaded_report_shape':shape==expected['cube_shape_band_y_x'],
             'matches_uploaded_report_epsg':epsg==str(expected['epsg_from_hdf5']),
             'candidate_official_scene_id':OFFICIAL_SCENE_ID,
             'official_public_asset_url':OFFICIAL_SOURCE_URL,
             'published_example_metadata_consistent':shape==[426,752,784] and epsg=='32721',
             'authenticated_against_publisher_hash':False,
             'explanation':'A locally computed SHA-256 only fingerprints the local file. It does not prove the file matches an official publisher checksum.'}
    if compute_hash:
        h=hashlib.sha256()
        with h5_path.open('rb') as f:
            for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
        results['local_sha256']=h.hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    (out/'scene_identity_audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return results


def main(argv=None):
    p=argparse.ArgumentParser(description='AgriLens spectral-information evidence, not diagnostic accuracy')
    cmd=p.add_subparsers(dest='command',required=True)
    a=cmd.add_parser('aggregate',help='Analyze user-provided Tanager-derived spectra: works offline')
    a.add_argument('--spectra',type=Path,default=Path('data/spectral_signatures.csv'))
    a.add_argument('--report',type=Path,default=Path('data/processing_report.json'))
    a.add_argument('--out',type=Path,default=Path('outputs'))
    b=cmd.add_parser('pixelwise',help='Use actual downloaded 1GB Tanager HDF5')
    b.add_argument('--h5',type=Path,required=True);b.add_argument('--out',type=Path,default=Path('outputs'))
    b.add_argument('--stride',type=int,default=8);b.add_argument('--max-pixels',type=int,default=1500)
    b.add_argument('--min-ndvi',type=float,default=.3)
    c=cmd.add_parser('verify-source',help='Check local scene against user report and fingerprint bytes')
    c.add_argument('--h5',type=Path,required=True)
    c.add_argument('--report',type=Path,default=Path('data/processing_report.json'))
    c.add_argument('--out',type=Path,default=Path('outputs'))
    c.add_argument('--skip-hash',action='store_true')
    args=p.parse_args(argv)
    if args.command=='aggregate': result=analyze_aggregates(args.spectra,args.report,args.out)
    elif args.command=='pixelwise': result=pixelwise_experiment(args.h5,args.out,args.stride,args.max_pixels,args.min_ndvi)
    else: result=verify_local_file(args.h5,args.report,args.out,not args.skip_hash)
    print(json.dumps(result,indent=2,default=_json_default))


if __name__=='__main__':main()
