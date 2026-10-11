import sys, json, hashlib, pandas as pd, numpy as np
out, root = sys.argv[1], sys.argv[2]; res=[]
def chk(name, ok, detail=''): res.append(dict(check=name, passed=bool(ok), detail=str(detail))); print(('PASS' if ok else 'FAIL'), name, detail)
M=json.load(open(f'{out}/verification/metrics.json'))
src=f'{root}/02_Field_Date_615/agrilens_real_field_date_QA_gated_615.csv'
man=pd.read_csv(f'{root}/SHA256_manifest.csv'); h=hashlib.sha256(open(src,'rb').read()).hexdigest()
chk('source sha256 equals team manifest', h==man[man.relative_path.str.endswith('QA_gated_615.csv')].sha256.iloc[0])
chk('source copy in package is byte-identical', hashlib.sha256(open(f'{out}/data/agrilens_real_field_date_QA_gated_615.csv','rb').read()).hexdigest()==h)
a=pd.read_csv(f'{out}/results/validated_anomalies_615.csv')
chk('615 rows, 20 fields, 33 dates', len(a)==615 and a.field_id.nunique()==20 and a.date.nunique()==33)
chk('no duplicate field-date', not a.duplicated(['field_id','date']).any())
chk('split 9/6/5 fields', a.groupby('split').field_id.nunique().to_dict()=={'test':5,'train':9,'validation':6})
chk('no field in two splits', (a.groupby('field_id').split.nunique()==1).all())
chk('excluded buffer fields absent', not a.field_id.isin([1664805,1664847,1664858]).any())
chk('no missing lon/lat/ndvi', a[['lon','lat','ndvi_mean']].notna().all().all())
chk('lon/lat inside AOI bounds', a.lon.between(30.20,30.30).all() and a.lat.between(30.58,30.68).all(), f'lon {a.lon.min():.4f}-{a.lon.max():.4f} lat {a.lat.min():.4f}-{a.lat.max():.4f}')
fl=a[a.flag]; chk('every flag has non-trivial category', (fl.flag_category!='no_flag').all() and (a[~a.flag].flag_category=='no_flag').all())
chk('flag count matches metrics', len(fl)==M['flags']==sum(M['flags_by_category'].values()))
chk('all AOT>=0.5 flags are artefact-suspect', (fl[(fl.aot_s2_mean>=.5)|(fl.aerosol_optical_depth>=.5)].flag_category=='scene_artifact_suspect').all())
chk('flags use |residual| > threshold, none missed', ((a.residual.abs()>M['threshold'])==a.flag).all() or ((a.residual.abs()>M['threshold'])&a.residual.notna()).sum()==a.flag.sum())
q=pd.read_csv(f'{out}/results/inspection_queue.csv'); chk('queue == flagged rows', len(q)==len(fl))
g=json.load(open(f'{out}/results/agrilens_validated_alerts.geojson')); chk('geojson features == flags', len(g['features'])==len(fl))
chk('geojson coordinates [lon,lat] valid', all(30<f['geometry']['coordinates'][0]<31 and 30<f['geometry']['coordinates'][1]<31 for f in g['features']))
# independent recompute of threshold from raw
d=pd.read_csv(src).sort_values(['field_id','date']); d['b']=d.groupby('field_id').ndvi_mean.transform(lambda s:s.shift(1).rolling(3,min_periods=1).median()); d['r']=d.ndvi_mean-d.b
tr=d[(d.field_split=='train')&d.r.notna()].r; thr=max(.05,3*1.4826*(tr-tr.median()).abs().median())
chk('threshold independently recomputed', abs(thr-M['threshold'])<1e-12, f'{thr:.5f}')
bn=pd.read_csv(f'{out}/results/forecast_benchmark_with_CI.csv'); t=bn[bn.split=='test'].set_index('model')
chk('test persistence MAE reproduces team 0.02752', abs(t.loc['persistence','MAE']-0.02752)<5e-6, t.loc['persistence','MAE'])
chk('test Ridge MAE reproduces team 0.03555', abs(t.loc['ridge_exploratory','MAE']-0.03555)<5e-6, t.loc['ridge_exploratory','MAE'])
chk('CI brackets point estimate', ((bn.MAE_CI95_low<=bn.MAE)&(bn.MAE<=bn.MAE_CI95_high)).all())
dq=pd.read_csv(f'{out}/results/date_scene_QA.csv'); chk('33 scene-QA dates; only 17 May has AOT>=0.5', len(dq)==33 and list(dq[dq.mean_aot_s2>=.5].date)==['2025-05-17'])

g=json.load(open(f'{root}/01_Sentinel2_original/ftw_aoi_sampling_frame.geojson'))
fg=pd.read_csv(f'{out}/results/field_geography.csv').set_index('field_id')
def flat(c):
    if isinstance(c[0],(int,float)): yield c
    else:
        for x in c: yield from flat(x)
mx=0;k=0
for ft in g['features']:
    try: fid=int(ft['properties']['field_id'])
    except Exception: continue
    if fid in fg.index:
        pts=np.array(list(flat(ft['geometry']['coordinates']))); c=(pts.min(0)+pts.max(0))/2; k+=1
        mx=max(mx,np.hypot((c[0]-fg.loc[fid,'lon'])*96000,(c[1]-fg.loc[fid,'lat'])*111000))
chk('field centroids agree with FTW polygons (<250 m from bbox centre)', k==20 and mx<250, f'{k} fields, max {mx:.0f} m')
import os
need=['figures/01_forecast_benchmark_CI.png','figures/02_scene_QA_by_date.png','figures/03_flags_by_field_map.png','AgriLens_Validation_Report.md','NOUR_HANDOFF.md','README.md']
chk('required files present', all(os.path.exists(f'{out}/{n}') for n in need))
rp=open(f'{out}/AgriLens_Validation_Report.md').read(); chk('report has no unfilled placeholders', '{' not in rp and 'nan' not in rp.lower().replace('financ',''))
json.dump(res,open(f'{out}/verification/verification_log.json','w'),indent=1)
bad=[r for r in res if not r['passed']]; print('\n',len(res)-len(bad),'/',len(res),'checks passed'); sys.exit(1 if bad else 0)
