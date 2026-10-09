#!/usr/bin/env python3
"""Evidence-first EnMAP L2A to Nile Delta Sentinel-2 field-level comparison.

Not an EnMAP 813 adapter or dust/drought classifier.

Commands:
    python scripts/enmap_egypt.py manifest
    python scripts/enmap_egypt.py probe
    python scripts/enmap_egypt.py download --auth
    python scripts/enmap_egypt.py process
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'config' / 'hsi_coverage_report.json'
AOI = ROOT / 'config' / 'egypt_aoi.geojson'
FRAME = ROOT / 'inputs' / 'ftw_aoi_sampling_frame.geojson'
S2_CSV = ROOT / 'inputs' / 'field_date_analysis.csv'
RASTER_DIR = ROOT / 'enmap' / 'egypt_20250720'
OUTPUT_DIR = ROOT / 'outputs'
REQUIRED_ASSET_KEYS = ('image','metadata','quality_cloud','quality_cloud_shadow','quality_haze','quality_classes','defective_pixel_mask')
SELECTED_CENTERS = {'blue':490., 'green':560.,'red':665.,'red_edge':705.,'nir':860.,'swir':1640.}
BAD_ATMOS_BANDS = [(0,400),(1350,1450),(1800,1980),(2450,2700)]
TIFF_MAGIC = (b'II*\x00',b'MM\x00*',b'II+\x00',b'MM\x00+')


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def scene_record(report_path=REPORT):
    report=load_json(report_path)
    scenes=report['coverage']['per_scene']
    if len(scenes)!=1:
        raise ValueError('Expected exactly one selected scene; review report before proceeding')
    scene=scenes[0]
    if not scene['id'].startswith('ENMAP01-____L2A-DT0000142619_20250720T092413Z_005_'):
        raise ValueError('Unexpected EnMAP scene: refusing accidental wrong-site processing')
    return scene


def make_manifest(scene):
    urls={'image':scene['image_url'],'metadata':scene['metadata_xml_url']}
    urls.update(scene['quality_asset_urls'])
    names={k:Path(url.split('?')[0]).name for k,url in urls.items()}
    for key,url in urls.items():
        if not url.startswith('https://download.geoservice.dlr.de/ENMAP/files/L2A/'):
            raise ValueError(f'Untrusted asset host/path for {key}')
    return {k:{'url':urls[k], 'filename':names[k], 'required':k in REQUIRED_ASSET_KEYS} for k in urls}


def file_kind_check(path, kind):
    path=Path(path)
    with path.open('rb') as f:
        start=f.read(1024)
    if kind=='metadata':
        if not start.lstrip().startswith((b'<?xml',b'<')) or b'<html' in start.lower():
            raise ValueError(f'{path.name} is not XML metadata (may be login page)')
    elif start[:4] not in TIFF_MAGIC:
        raise ValueError(f'{path.name} is not a TIFF (may be login page)')
    return True


def _build_session(auth=False):
    import requests
    sess=requests.Session()
    sess.headers['User-Agent']='AgriLens-EnMAP-Acquisition/1.0 (research)'
    if auth:
        username=input('EnMAP IPS/EOWEB username: ').strip()
        password=getpass.getpass('EnMAP password (not saved): ')
        if not username or not password:
            raise ValueError('Both username and password required')
        sess.auth=(username,password)
    return sess


def probe_assets(manifest, out_path, auth=False):
    sess=_build_session(auth)
    results={}
    for key, entry in manifest.items():
        try:
            # Stream to prevent downloading the full remote TIFF during probe.
            with sess.get(entry['url'],headers={'Range':'bytes=0-31'},
                          timeout=(10,45),stream=True,allow_redirects=True) as response:
                start=next(response.iter_content(chunk_size=64), b'')
                ok=(response.status_code in (200,206) and
                    ((start[:4] in TIFF_MAGIC) if key!='metadata'
                     else (start.lstrip().startswith((b'<?xml',b'<')) and b'<html' not in start.lower())))
                results[key]={'http_status':response.status_code,
                              'content_type':response.headers.get('Content-Type'),
                              'final_url_host':__import__('urllib.parse',fromlist=['urlparse']).urlparse(response.url).hostname,
                              'asset_signature_verified':bool(ok),
                              'redirected':bool(response.history),
                              'size_header':response.headers.get('Content-Length'),
                              'reason':('Valid file signature' if ok else 'Not authenticated / unavailable / response not original asset')}
        except Exception as e:
            results[key]={'asset_signature_verified':False,'reason':f'{type(e).__name__}: {str(e)[:200]}'}
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps({'access_only_not_local_data_QA':True,'assets':results},indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
    return all(results[k]['asset_signature_verified'] for k in REQUIRED_ASSET_KEYS)


def download_assets(manifest, dest, auth=False, keys=None, max_gib=10):
    sess=_build_session(auth)
    dest.mkdir(parents=True,exist_ok=True)
    keys=keys or list(manifest)
    for key in keys:
        entry=manifest[key]
        target=dest / entry['filename']
        if target.exists():
            file_kind_check(target,key)
            print('Existing valid-format file (not cryptographically authenticated):',target.name)
            continue
        partial=target.with_name(target.name+'.part')
        if partial.exists():
            raise RuntimeError(f'Partial file exists: {partial}; inspect/close downloads and remove or rename it manually. No automatic deletion.')
        byte_count=0
        try:
            with sess.get(entry['url'],timeout=(20,90),stream=True,allow_redirects=True) as r:
                r.raise_for_status()
                if __import__('urllib.parse',fromlist=['urlparse']).urlparse(r.url).hostname != 'download.geoservice.dlr.de':
                    raise RuntimeError(f'{key}: redirected away from official download host (authentication may be needed)')
                declared=int(r.headers.get('Content-Length') or '0')
                if declared > max_gib*(1024**3):
                    raise RuntimeError(f'{key}: {declared} bytes exceeds --max-gib limit')
                with partial.open('wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk:
                            if byte_count==0:
                                if key=='metadata':
                                    if b'<html' in chunk[:1024].lower() or not chunk.lstrip().startswith(b'<'):
                                        raise RuntimeError('Not XML metadata; authentication probably required')
                                elif chunk[:4] not in TIFF_MAGIC:
                                    raise RuntimeError('Not a GeoTIFF; authentication probably required')
                            byte_count+=len(chunk)
                            if byte_count > max_gib*(1024**3):
                                raise RuntimeError('Downloaded data exceeds size limit')
                            f.write(chunk)
                if declared and byte_count!=declared:
                    raise RuntimeError(f'Incomplete download: expected {declared}, got {byte_count}')
            file_kind_check(partial,key)
            partial.replace(target)
            print(f'Downloaded {key}: {target} ({byte_count} bytes)')
        except Exception:
            # Keep partial for audit and to avoid Windows open-file deletion errors.
            print('Failed asset download; partial data, if any, left at',partial,file=sys.stderr)
            raise


def local_name(tag):
    return tag.rsplit('}',1)[-1]


def parse_band_metadata(path):
    """Read official EnMAP bandCharacterisation/bandID table.

    Never invent wavelengths, units or gains if unavailable.
    """
    tree=ET.parse(path)
    bands=[]
    for elem in tree.iter():
        if local_name(elem.tag) != 'bandID' or not elem.attrib.get('number'):
            continue
        children={local_name(c.tag):(c.text or '').strip() for c in elem}
        center=children.get('wavelengthCenterOfBand')
        if not center:
            continue
        bands.append({'number':int(elem.attrib['number']),
                      'wavelength_nm':float(center),
                      'fwhm_nm':float(children['FWHMOfBand']) if children.get('FWHMOfBand') else None,
                      'gain':float(children['GainOfBand']) if children.get('GainOfBand') else None,
                      'offset':float(children['OffsetOfBand']) if children.get('OffsetOfBand') else None})
    if not bands:
        raise ValueError('No bandCharacterisation/bandID wavelength table found in XML')
    bands.sort(key=lambda b:b['number'])
    if [b['number'] for b in bands] != list(range(1,len(bands)+1)):
        raise ValueError('Band numbering in XML is not contiguous')
    if any(not 300<=b['wavelength_nm']<=2700 for b in bands):
        raise ValueError('Implausible EnMAP wavelength in XML')
    return bands


def selected_band_indices(bands,tolerance_nm=25):
    w=np.array([b['wavelength_nm'] for b in bands],dtype=float)
    selected={}
    for name,center in SELECTED_CENTERS.items():
        idx=int(np.abs(w-center).argmin())
        if abs(w[idx]-center)>tolerance_nm:
            raise ValueError(f'Missing sufficiently close {name} band ({center} nm); nearest {w[idx]:.2f} nm')
        selected[name]=idx
    return selected


def compute_indices(red,nir,red_edge,swir,valid):
    def norm(a,b):
        den=a+b
        return np.where(valid & (np.abs(den)>1e-8), (a-b)/np.where(np.abs(den)>1e-8,den,1),np.nan).astype('float32')
    return {'ndvi':norm(nir,red),'ndre':norm(nir,red_edge),'ndmi':norm(nir,swir)}


def load_aoi_geom(aoi_path):
    from shapely.geometry import shape
    obj=load_json(aoi_path)
    if obj.get('type')=='FeatureCollection':
        if len(obj['features'])!=1:
            raise ValueError('AOI must have one polygon')
        return shape(obj['features'][0]['geometry'])
    return shape(obj['geometry'] if obj.get('type')=='Feature' else obj)


def reproject_geom(geom,src,dst):
    from shapely.ops import transform
    from pyproj import Transformer
    if str(src)==str(dst):return geom
    t=Transformer.from_crs(src,dst,always_xy=True)
    return transform(t.transform, geom)


def quality_band_aligned(qpath, shape_, window_transform, dst_crs):
    import rasterio
    from rasterio.warp import reproject,Resampling
    dest=np.full(shape_,-9999,dtype='int32')
    with rasterio.open(qpath) as q:
        if q.count != 1: raise ValueError(f'Quality layer must be single band: {qpath}')
        reproject(source=rasterio.band(q,1),destination=dest,
                  src_transform=q.transform, src_crs=q.crs,src_nodata=q.nodata,
                  dst_transform=window_transform,dst_crs=dst_crs,dst_nodata=-9999,
                  resampling=Resampling.nearest)
    return dest


def band_scale_and_offset(bands,dataset):
    gains=[];offsets=[]
    for i,b in enumerate(bands):
        if b['gain'] is not None:
            gains.append(b['gain']);offsets.append(b['offset'] or 0)
        elif dataset.scales[i] not in (None,0,1):
            gains.append(dataset.scales[i]);offsets.append(dataset.offsets[i] or 0)
        elif np.issubdtype(np.dtype(dataset.dtypes[i]),np.floating):
            gains.append(1);offsets.append(0)
        else:
            raise ValueError(f'No gain/offset for integer band {i+1}. Refuse to assume 1/10000.')
    if any(x<=0 for x in gains):
        raise ValueError('Nonpositive reflectance gains')
    return np.asarray(gains,dtype='float32'), np.asarray(offsets,dtype='float32')


def expected_file_paths(manifest,folder):
    return {key:folder/entry['filename'] for key,entry in manifest.items()}


def build_field_id_grid(field_geojson, scene_crs,window_transform,shape_):
    from rasterio.features import rasterize
    from shapely.geometry import shape,mapping
    frame=load_json(field_geojson)
    features=[];mapids={}; excluded=[]
    for f in frame['features']:
        p=f['properties'];fid=str(p['field_id'])
        if p.get('selection_status') not in ('train','validation','test'):
            excluded.append({'field_id':fid,'reason':p.get('selection_status')});continue
        number=len(features)+1
        polygon=reproject_geom(shape(f['geometry']),'EPSG:4326',scene_crs)
        features.append((mapping(polygon),number))
        mapids[number]={'field_id':fid,'field_split':p.get('selection_status')}
    grid=rasterize(features,out_shape=shape_,transform=window_transform,fill=0,dtype='int32')
    return grid,mapids,excluded


def run_processing(scene,manifest,folder,aoi_path,field_path,s2_csv,out,expected_bands=224,
                   allow_missing_masks=False,sample_pixels=200):
    import rasterio
    from rasterio.windows import Window
    from rasterio.features import geometry_window,geometry_mask
    from shapely.geometry import box,mapping
    out.mkdir(parents=True,exist_ok=True)
    paths=expected_file_paths(manifest,folder)
    for key in ('image','metadata'):
        if not paths[key].exists():
            raise FileNotFoundError(f'Missing {key}: {paths[key]}')
        file_kind_check(paths[key],key)
    bands=parse_band_metadata(paths['metadata'])
    xml_text=paths['metadata'].read_text(encoding='utf-8',errors='replace')
    observed_datatakes=sorted(set(re.findall(r'DT\d{10}',xml_text)))
    if observed_datatakes and 'DT0000142619' not in observed_datatakes:
        raise ValueError('Metadata XML mentions different datatake: '+','.join(observed_datatakes))
    metadata_scene_reference_detected=('DT0000142619' in xml_text or scene['id'] in xml_text)
    if expected_bands is not None and len(bands)!=expected_bands:
        raise ValueError(f'XML band count {len(bands)} differs from expected {expected_bands}')
    selected=selected_band_indices(bands)
    missing_masks=[key for key in REQUIRED_ASSET_KEYS if key.startswith('quality_') or key=='defective_pixel_mask' if not paths[key].exists()]
    if missing_masks and not allow_missing_masks:
        raise FileNotFoundError(f'Missing required quality masks {missing_masks}; use --allow-missing-masks ONLY for exploratory incomplete QA')
    aoi=load_aoi_geom(aoi_path)
    with rasterio.open(paths['image']) as ds:
        if ds.count!=len(bands):
            raise ValueError(f'Raster bands {ds.count} do not match XML {len(bands)}')
        if not ds.crs:
            raise ValueError('Raster missing CRS')
        projected_aoi=reproject_geom(aoi,'EPSG:4326',ds.crs)
        try:
            win=geometry_window(ds,[mapping(projected_aoi)],pad_x=0,pad_y=0)
        except rasterio.errors.WindowError as e:
            raise ValueError('AOI has no overlap with EnMAP raster') from e
        wt=ds.window_transform(win)
        shape_=(int(win.height),int(win.width))
        aoi_mask=geometry_mask([mapping(projected_aoi)],transform=wt,out_shape=shape_,invert=True)
        # Geographic coverage independent of catalog footprint.
        rasterfoot=box(*ds.bounds)
        aoi_metric=reproject_geom(projected_aoi,ds.crs,'EPSG:32636')
        footmetric=reproject_geom(rasterfoot,ds.crs,'EPSG:32636')
        coverage=float(aoi_metric.intersection(footmetric).area/aoi_metric.area)
        if coverage < 0.99:
            raise ValueError(f'Insufficient actual raster/AOI coverage: {coverage:.5f}')
        arr=ds.read(window=win,masked=True).astype('float32')
        gains,offsets=band_scale_and_offset(bands,ds)
        cube=np.asarray(arr.filled(np.nan),dtype='float32')*gains[:,None,None]+offsets[:,None,None]
        bad_raw=np.ma.getmaskarray(arr)
        if bad_raw.any(): cube[bad_raw]=np.nan
        # Preserve physically suspect bands as missing rather than zero-filling.
        missingbands=np.array([any(lo<=b['wavelength_nm']<=hi for lo,hi in BAD_ATMOS_BANDS) for b in bands])
        cube[missingbands]=np.nan
        quality=aoi_mask.copy()
        mask_counts={}
        for key in ('quality_cloud','quality_cloud_shadow','quality_haze','defective_pixel_mask'):
            if paths[key].exists():
                v=quality_band_aligned(paths[key],shape_,wt,ds.crs)
                valid=v!=-9999
                # Require known flag values; excluded where flagged or quality missing.
                blocked=(v!=0) | ~valid
                quality &= ~blocked
                mask_counts[key+'_flagged_or_nodata_in_aoi']=int(np.count_nonzero(blocked & aoi_mask))
        # Optional quality_classes: class=1 is land, 2 water, 3 nodata per EnMAP docs.
        if paths.get('quality_classes',Path('/nonexistent')).exists():
            v=quality_band_aligned(paths['quality_classes'],shape_,wt,ds.crs)
            blocked=(v!=1)
            quality &= ~blocked
            mask_counts['nonland_or_unclassified_in_aoi']=int(np.count_nonzero(blocked & aoi_mask))
        # Flag missing optional cirrus imagery in report rather than treating absent as clear.
        optional_cirrus=list(folder.glob('*QL_QUALITY_CIRRUS*.TIF'))
        if optional_cirrus:
            v=quality_band_aligned(optional_cirrus[0],shape_,wt,ds.crs)
            blocked=v!=0
            quality &= ~blocked
            mask_counts['cirrus_flagged_or_nodata_in_aoi']=int(np.count_nonzero(blocked & aoi_mask))
        else:
            mask_counts['cirrus_asset_present']=False
        needed=np.stack([cube[selected[n]] for n in ('red','nir','red_edge','swir')])
        reflectance_valid=np.all(np.isfinite(needed)&(needed>=0)&(needed<=1.2),axis=0)
        good=quality & reflectance_valid
        if not np.any(good):
            raise ValueError('No good Egypt AOI pixels remain after QA, cannot extract spectra')
        indices=compute_indices(cube[selected['red']],cube[selected['nir']],cube[selected['red_edge']],cube[selected['swir']],good)
        fields_grid,field_map,excluded=build_field_id_grid(field_path,ds.crs,wt,shape_)
        # Save rasters in native EnMAP pixels; do not upsample 30m into pretend 20m details.
        ndvi_profile=ds.profile.copy()
        ndvi_profile.update(count=4,height=shape_[0],width=shape_[1],transform=wt,
                            dtype='float32',nodata=-9999,compress='deflate')
        with rasterio.open(out/'egypt_enmap_indices_30m.tif','w',**ndvi_profile) as d:
            for idx,name in enumerate(('ndvi','ndre','ndmi'),1):
                d.write(np.where(np.isfinite(indices[name]),indices[name],-9999),idx)
                d.set_band_description(idx,name.upper())
            d.write(good.astype('float32'),4)
            d.set_band_description(4,'QA_VALID_BINARY')
        wavelengths=[b['wavelength_nm'] for b in bands]
        # Selected valid pixel spectra only; absent narrow-band values stay nan.
        rr,cc=np.nonzero(good)
        take=np.linspace(0,len(rr)-1,num=min(sample_pixels,len(rr)),dtype='int64')
        samples=[]
        for r,c in zip(rr[take],cc[take]):
            x,y=rasterio.transform.xy(wt,int(r),int(c))
            fid=field_map.get(int(fields_grid[r,c]),{})
            for j,b in enumerate(bands):
                val=cube[j,r,c]
                samples.append({'field_id':fid.get('field_id'), 'x_scene_crs':x,'y_scene_crs':y,
                                'wavelength_nm':b['wavelength_nm'],
                                'reflectance':float(val) if np.isfinite(val) and 0<=val<=1.2 else np.nan})
        pd.DataFrame(samples).to_csv(out/'egypt_pixel_spectra_long.csv',index=False)
        fieldrows=[]
        for n,info in field_map.items():
            sel=(fields_grid==n)&good
            npx=int(sel.sum())
            if npx==0:continue
            record={'field_id':info['field_id'],'field_split':info['field_split'],
                    'enmap_acquisition_utc':scene['acquisition_datetime_utc'],
                    'enmap_valid_pixels':npx,'enmap_resolution_m':abs(ds.res[0]),
                    'enmap_sensor':'EnMAP L2A'}
            for k,v in indices.items():
                record['enmap_'+k+'_median']=float(np.nanmedian(v[sel]))
                record['enmap_'+k+'_mean']=float(np.nanmean(v[sel]))
            fieldrows.append(record)
        fielddf=pd.DataFrame(fieldrows)
        if fielddf.empty:raise ValueError('No usable geometrically valid field pixel overlap')
        fielddf.to_csv(out/'egypt_enmap_field_indices.csv',index=False)
        # Field spectral summary: full wavelength-per-field feature table, not crop labels.
        with (out/'egypt_enmap_field_spectra.csv').open('w',newline='',encoding='utf-8') as h:
            writer=csv.DictWriter(h,fieldnames=['field_id','wavelength_nm','median_reflectance','valid_pixels'])
            writer.writeheader()
            for n,info in field_map.items():
                sel=(fields_grid==n)&good
                if not sel.any():continue
                for i,band in enumerate(bands):
                    vals=cube[i][sel]
                    vals=vals[np.isfinite(vals)&(vals>=0)&(vals<=1.2)]
                    writer.writerow({'field_id':info['field_id'],'wavelength_nm':band['wavelength_nm'],
                                    'median_reflectance':float(np.median(vals)) if len(vals) else '',
                                    'valid_pixels':len(vals)})
        s2=pd.read_csv(s2_csv,dtype={'field_id':str})
        s2['date']=pd.to_datetime(s2['date'])
        target=pd.Timestamp(scene['acquisition_datetime_utc']).tz_convert(None).normalize()
        s2['days_from_enmap']=(s2['date']-target).dt.days
        s2=s2[s2['days_from_enmap'].abs()<=3].copy()
        if not s2.empty:
            s2=s2.loc[s2.groupby('field_id')['days_from_enmap'].transform(lambda x: x.abs()==x.abs().min())]
            s2=s2.sort_values(['field_id','date']).drop_duplicates('field_id')
        join=fielddf.merge(s2[['field_id','date','days_from_enmap','ndvi_mean','ndmi_mean','pixel_count']],
                           on='field_id',how='left',validate='one_to_one')
        join=join.rename(columns={'date':'s2_date','ndvi_mean':'s2_ndvi_mean','ndmi_mean':'s2_ndmi_mean','pixel_count':'s2_pixel_count'})
        join['enmap_minus_s2_ndvi']=join.enmap_ndvi_mean-join.s2_ndvi_mean
        join['sensors_not_equivalent_note']='Comparison only: 30m vs 20m, different spectral responses and +/-3-day timing'
        join.to_csv(out/'egypt_enmap_sentinel2_field_alignment.csv',index=False)
        # Asset provenance: each local file hash, no credentials, verify relative to external checksum separately.
        assets={}
        for k,p in paths.items():
            if p.exists():
                hh=hashlib.sha256()
                with p.open('rb') as f:
                    for chunk in iter(lambda:f.read(8*1024*1024),b''):hh.update(chunk)
                assets[k]={'filename':p.name,'sha256_local':hh.hexdigest(),'bytes':p.stat().st_size,
                           'official_checksum_compared':False}
        report={'status':'LOCAL_ENMAP_PIXEL_QA_COMPLETED_SOURCE_CHECKSUM_NOT_VERIFIED',
                'scene_id':scene['id'],'acquisition_datetime_utc':scene['acquisition_datetime_utc'],
                'aoi_coverage_fraction_measured_from_raster':coverage,
                'aoi_area_sq_km_from_projected_geometry':aoi_metric.area/1e6,
                'raster_bands':ds.count,'xml_bands':len(bands),
                'scene_crs':str(ds.crs),'raster_resolution_m':list(ds.res),
                'aoi_pixel_centers':int(aoi_mask.sum()),
                'valid_indices_pixel_centers':int(good.sum()),
                'valid_indices_fraction':float(good.sum()/max(aoi_mask.sum(),1)),
                'complete_mask_set':not missing_masks,
                'missing_required_quality_masks':missing_masks,
                'quality_mask_exclusion_counts_nonadditive':mask_counts,
                'selected_wavelengths_nm':{k:float(bands[v]['wavelength_nm']) for k,v in selected.items()},
                'bands_excluded_atmospheric_ranges':int(missingbands.sum()),
                'field_count_with_valid_enmap_pixels':len(fielddf),
                'field_count_with_sentinel2_match':int(join['s2_date'].notna().sum()),
                's2_max_days_from_enmap':3,
                'exclusions_from_previous_field_QA':excluded,
                'assets':assets,
                'limitations':['No independent crop stress labels','One EnMAP date is not a hyperspectral time series',
                               'No claim of Satellite 813 data','S2 cross-sensor differences include band response, resolution and timing',
                               'SHA256 of downloaded asset not yet compared to independently published source digest']}
        (out/'egypt_enmap_validation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action',choices=['manifest','probe','download','process'])
    ap.add_argument('--report',type=Path,default=REPORT)
    ap.add_argument('--aoi',type=Path,default=AOI)
    ap.add_argument('--field-geojson',type=Path,default=FRAME)
    ap.add_argument('--s2',type=Path,default=S2_CSV)
    ap.add_argument('--folder',type=Path,default=RASTER_DIR)
    ap.add_argument('--out',type=Path,default=OUTPUT_DIR)
    ap.add_argument('--auth',action='store_true',help='Prompt for DLR IPS/EOWEB username and password (never saved)')
    ap.add_argument('--keys',nargs='+',help='Subset of download assets, e.g. image metadata quality_cloud')
    ap.add_argument('--max-gib',type=int,default=10)
    ap.add_argument('--expected-bands',type=int,default=224)
    ap.add_argument('--sample-pixels',type=int,default=200)
    ap.add_argument('--allow-missing-masks',action='store_true',help='Exploratory output only: QA report marks missing masks')
    args=ap.parse_args(argv)
    scene=scene_record(args.report)
    manifest=make_manifest(scene)
    if args.action=='manifest':
        args.out.mkdir(parents=True,exist_ok=True)
        p=args.out/'egypt_enmap_asset_manifest.json'
        p.write_text(json.dumps({'scene_id':scene['id'],'from_cached_catalog':True,'assets':manifest},indent=2),encoding='utf-8')
        print('Wrote:',p)
        for k,v in manifest.items():print(k, v['filename'])
    elif args.action=='probe':
        ok=probe_assets(manifest,args.out/'egypt_enmap_access_probe.json',auth=args.auth)
        if not ok:raise SystemExit('Some assets could not be authenticated or accessed; see outputs/egypt_enmap_access_probe.json')
    elif args.action=='download':
        if args.keys and any(k not in manifest for k in args.keys):
            raise ValueError('Invalid asset keys: '+','.join(k for k in args.keys if k not in manifest))
        download_assets(manifest,args.folder,auth=args.auth,keys=args.keys,max_gib=args.max_gib)
    elif args.action=='process':
        r=run_processing(scene,manifest,args.folder,args.aoi,args.field_geojson,args.s2,args.out,
                         expected_bands=args.expected_bands,allow_missing_masks=args.allow_missing_masks,
                         sample_pixels=args.sample_pixels)
        print(json.dumps({k:r[k] for k in ('status','aoi_coverage_fraction_measured_from_raster','valid_indices_pixel_centers','valid_indices_fraction','field_count_with_valid_enmap_pixels','field_count_with_sentinel2_match')},indent=2))


if __name__=='__main__':
    main()
