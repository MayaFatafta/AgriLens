"""AgriLens Validation FINAL builder. Usage: build.py <team_dataset_root> <out_dir>"""
import sys, os, json, hashlib, shutil
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from pyproj import Transformer
root, out = sys.argv[1], sys.argv[2]
for sub in ['data','results','figures','verification','scripts']: os.makedirs(f'{out}/{sub}', exist_ok=True)
SRC615=f'{root}/02_Field_Date_615/agrilens_real_field_date_QA_gated_615.csv'
d=pd.read_csv(SRC615, parse_dates=['date']).sort_values(['field_id','date']).reset_index(drop=True)
d['split']=d.field_split
# --- baseline / residual / threshold (train fields only)
g=d.groupby('field_id').ndvi_mean
d['baseline_prior3']=g.transform(lambda s:s.shift(1).rolling(3,min_periods=1).median())
d['residual']=d.ndvi_mean-d.baseline_prior3
tr=d[(d.split=='train')&d.residual.notna()].residual
med=tr.median(); mad=(tr-med).abs().median(); thr=max(.05,3*1.4826*mad)
d['flag']=d.residual.abs()>thr
d['direction']=np.where(d.residual<0,'low','high')
# --- per field-date pixel QA from the source pixel table
p=pd.read_parquet(f'{root}/01_Sentinel2_original/dataset.parquet',columns=['date','scl','aot_s2','ndvi','field_id'])
p['field_id']=pd.to_numeric(p.field_id,errors='coerce'); p=p[p.field_id.isin(d.field_id.unique())].copy(); p['date']=pd.to_datetime(p.date)
fq=p.groupby(['field_id','date']).agg(scl7_share=('scl',lambda s:(s==7).mean()),scl5_share=('scl',lambda s:(s==5).mean()),pixels_src=('scl','size')).reset_index()
d=d.merge(fq,on=['field_id','date'],how='left'); assert d.scl7_share.notna().all()
dq=p.groupby('date').agg(mean_aot_s2=('aot_s2','mean'),scl4_share=('scl',lambda s:(s==4).mean()),scl5_share=('scl',lambda s:(s==5).mean()),scl7_share=('scl',lambda s:(s==7).mean()),n_pixels=('scl','size')).reset_index()
rn=d.groupby('date').agg(regional_mean_ndvi=('ndvi_mean','mean'),fields=('field_id','nunique')).reset_index()
dq=dq.merge(rn,on='date'); dq['regional_ndvi_prev_obs']=dq.regional_mean_ndvi.shift(1); dq['regional_ndvi_next_obs']=dq.regional_mean_ndvi.shift(-1)
dq['regional_drop_vs_prev']=dq.regional_mean_ndvi-dq.regional_ndvi_prev_obs
dq['regional_rebound_to_next']=dq.regional_ndvi_next_obs-dq.regional_mean_ndvi
nfl=d[d.flag].groupby('date').size(); dq['n_flags']=dq.date.map(nfl).fillna(0).astype(int)
dq['scene_qa_note']=np.where(dq.mean_aot_s2>=0.5,'HIGH regional AOT: treat dips as suspected scene/atmospheric artefact until imagery is checked','')
dq.to_csv(f'{out}/results/date_scene_QA.csv',index=False,float_format='%.5f')
# --- categories
d['aot_high']=(d.aot_s2_mean>=0.5)|(d.aerosol_optical_depth>=0.5)
d['long_gap']=d.days_since_prev>10
def cat(r):
    if not r.flag: return 'no_flag'
    if r.aot_high: return 'scene_artifact_suspect'
    if r.scl7_share>=0.10: return 'unclassified_pixels_review'
    if r.long_gap: return 'long_gap_review'
    return 'review'
d['flag_category']=d.apply(cat,axis=1)
NOTE={'no_flag':'No automatic flag','scene_artifact_suspect':'Do NOT count as damage: high AOT (>=0.5) scene; verify SCL/imagery first','unclassified_pixels_review':'>=10% of pixels are SCL 7 (unclassified); possible atmospheric artefact; verify imagery','long_gap_review':'Change spans >10 days between observations; low confidence','review':'NDVI deviates from prior-3 baseline; needs independent field evidence (no causal claim)'}
d['review_note']=d.flag_category.map(NOTE)
# --- coordinates (field centroids, EPSG:32636 -> WGS84)
sf=pd.read_csv(f'{root}/01_Sentinel2_original/sampling_frame_and_splits.csv')
tf=Transformer.from_crs(32636,4326,always_xy=True)
sf['lon'],sf['lat']=tf.transform(sf.centroid_x_utm.values,sf.centroid_y_utm.values)
d=d.merge(sf[['field_id','area_ha','lon','lat']],on='field_id',how='left'); assert d.lon.notna().all()
# --- outputs: anomalies
cols=['field_id','date','split','ndvi_mean','baseline_prior3','residual','flag','flag_category','direction','aot_s2_mean','aerosol_optical_depth','dust','scl7_share','scl5_share','days_since_prev','area_ha','lon','lat','review_note']
a=d[cols].copy(); a['date']=a.date.dt.date; a.to_csv(f'{out}/results/validated_anomalies_615.csv',index=False,float_format='%.6f')
q=a[a.flag].copy(); q['order']=q.flag_category.map({'review':0,'long_gap_review':1,'unclassified_pixels_review':2,'scene_artifact_suspect':3}); q=q.sort_values(['order','residual']).drop(columns='order'); q.to_csv(f'{out}/results/inspection_queue.csv',index=False,float_format='%.6f')
feats=[{"type":"Feature","geometry":{"type":"Point","coordinates":[round(r.lon,6),round(r.lat,6)]},"properties":{"field_id":int(r.field_id),"date":str(r.date),"split":r.split,"residual":round(float(r.residual),4),"direction":r.direction,"flag_category":r.flag_category,"note":r.review_note}} for r in d[d.flag].itertuples()]
json.dump({"type":"FeatureCollection","name":"agrilens_validated_alerts","features":feats},open(f'{out}/results/agrilens_validated_alerts.geojson','w'))
# --- forecast benchmark with field-cluster bootstrap CI
n=pd.read_csv(f'{root}/04_NDVI_forecasting/next_ndvi_regression.csv',parse_dates=['date'])
pr=pd.read_csv(f'{root}/04_NDVI_forecasting/regression_predictions.csv',parse_dates=['date'])
d['median_last3']=d.groupby('field_id').ndvi_mean.transform(lambda s:s.rolling(3,min_periods=1).median())
n=n.merge(pr[['field_id','date','ridge_pred_ndvi']],on=['field_id','date']).merge(d[['field_id','date','median_last3']],on=['field_id','date'])
rng=np.random.default_rng(20261011); B=5000; rows=[]; diffs=[]
for sp in ['validation','test']:
    s=n[n.ml_split==sp].reset_index(drop=True); fl=s.field_id.unique(); y=s.target_ndvi_next.values
    pred={'persistence':s.ndvi_mean.values,'median_last3':s.median_last3.values,'ridge_exploratory':s.ridge_pred_ndvi.values}
    ae={k:np.abs(v-y) for k,v in pred.items()}; idx={f:np.where(s.field_id.values==f)[0] for f in fl}
    boots={k:[] for k in ae}; dboot=[]
    for _ in range(B):
        ch=rng.choice(fl,len(fl),replace=True); ii=np.concatenate([idx[f] for f in ch])
        for k in ae: boots[k].append(ae[k][ii].mean())
        dboot.append(ae['ridge_exploratory'][ii].mean()-ae['persistence'][ii].mean())
    for k in ae:
        lo,hi=np.percentile(boots[k],[2.5,97.5]); rows.append(dict(split=sp,model=k,pairs=len(s),fields=len(fl),MAE=ae[k].mean(),RMSE=float(np.sqrt(((pred[k]-y)**2).mean())),MAE_CI95_low=lo,MAE_CI95_high=hi))
    lo,hi=np.percentile(dboot,[2.5,97.5]); diffs.append(dict(split=sp,contrast='ridge minus persistence (MAE)',point=ae['ridge_exploratory'].mean()-ae['persistence'].mean(),CI95_low=lo,CI95_high=hi,fraction_boot_ridge_better=float(np.mean(np.array(dboot)<0))))
bench=pd.DataFrame(rows); bench.to_csv(f'{out}/results/forecast_benchmark_with_CI.csv',index=False,float_format='%.5f')
diff=pd.DataFrame(diffs); diff.to_csv(f'{out}/results/ridge_vs_persistence_contrast.csv',index=False,float_format='%.5f')
# --- geographic bias
fld=d.groupby('field_id').agg(split=('split','first'),area_ha=('area_ha','first'),lon=('lon','first'),lat=('lat','first'),field_dates=('date','size'),with_baseline=('baseline_prior3',lambda s:s.notna().sum()),flags_total=('flag','sum'),
   flags_review=('flag_category',lambda s:s.isin(['review','long_gap_review','unclassified_pixels_review']).sum()),flags_artifact_suspect=('flag_category',lambda s:(s=='scene_artifact_suspect').sum())).reset_index()
fld['review_flag_rate']=fld.flags_review/fld.with_baseline
emit=pd.read_csv(f'{root}/03_EMIT_hyperspectral/EMIT_master_20_fields.csv'); 
ecol=[c for c in emit.columns if 'usable' in c.lower() or 'valid' in c.lower()]; 
fld.to_csv(f'{out}/results/field_geography.csv',index=False,float_format='%.5f')
sp_sum=fld.groupby('split').agg(fields=('field_id','size'),mean_lon=('lon','mean'),mean_lat=('lat','mean'),mean_area_ha=('area_ha','mean'),rows_with_baseline=('with_baseline','sum'),flags_total=('flags_total','sum'),flags_review=('flags_review','sum'),flags_artifact=('flags_artifact_suspect','sum')).reset_index()
sp_sum['review_flag_rate']=sp_sum.flags_review/sp_sum.rows_with_baseline
eb=pd.read_csv(f'{root}/03_EMIT_hyperspectral/EMIT_selection_bias_by_split.csv').rename(columns={'eligible_fields':'emit_eligible','usable_emit_fields':'emit_usable','mean_coverage':'emit_mean_coverage'})
sp_sum=sp_sum.merge(eb[['field_split','emit_usable','emit_mean_coverage']].rename(columns={'field_split':'split'}),on='split'); sp_sum.to_csv(f'{out}/results/geographic_bias_by_split.csv',index=False,float_format='%.5f')
# --- figures
BL,OR,GR='#1b6ca8','#d0602e','#8a8a8a'
fig,ax=plt.subplots(1,2,figsize=(11,4),sharey=True)
cm={'persistence':BL,'median_last3':GR,'ridge_exploratory':OR}
for i,sp in enumerate(['validation','test']):
    b=bench[bench.split==sp].reset_index(drop=True)
    ax[i].bar(b.model,b.MAE,color=[cm[m] for m in b.model],yerr=[b.MAE-b.MAE_CI95_low,b.MAE_CI95_high-b.MAE],capsize=4)
    for j,v in enumerate(b.MAE): ax[i].text(j,0.001,f'{v:.4f}',ha='center',color='white',fontsize=9)
    ax[i].set_title(f'{sp.capitalize()} ({int(b.pairs[0])} pairs, {int(b.fields[0])} fields)'); ax[i].set_xticks(range(3)); ax[i].set_xticklabels(['persistence','median\nlast 3','Ridge\n(exploratory)'])
ax[0].set_ylabel('Next-observation NDVI MAE (95% field-bootstrap CI)'); fig.suptitle('Ridge beats persistence on validation but not on the held-out test (intervals overlap)',fontsize=11); plt.tight_layout(); plt.savefig(f'{out}/figures/01_forecast_benchmark_CI.png',dpi=150); plt.close()
fig,ax=plt.subplots(2,1,figsize=(11,6.2),sharex=True,gridspec_kw={'height_ratios':[2,1.2]})
x=dq.date; ax[0].plot(x,dq.regional_mean_ndvi,color=BL,marker='o',ms=4); ax[0].set_ylabel('Mean NDVI, all 20 fields')
hi=dq[dq.mean_aot_s2>=0.5]
for r in hi.itertuples(): ax[0].axvline(r.date,color=OR,alpha=.4,lw=6); ax[0].text(r.date+pd.Timedelta(days=6),r.regional_mean_ndvi+0.004,f'{r.date:%d %b}: mean AOT {r.mean_aot_s2:.2f}, SCL 5 = {r.scl5_share:.0%} of pixels',color=OR,fontsize=9)
ax[1].bar(x,dq.n_flags,width=3,color=[OR if v>=.5 else BL for v in dq.mean_aot_s2]); ax[1].set_ylabel('Flagged observations')
ax[0].set_title('Regional NDVI dip on 17 May coincides with the highest AOT and rebounds by 20 May',fontsize=11); plt.tight_layout(); plt.savefig(f'{out}/figures/02_scene_QA_by_date.png',dpi=150); plt.close()
fig,ax=plt.subplots(figsize=(9,4.6)); sc={'train':BL,'validation':'#3a9a5b','test':OR}
for sp,gdf in fld.groupby('split'):
    ax.scatter(gdf.lon,gdf.lat,s=60+gdf.flags_review*45,color=sc[sp],alpha=.75,edgecolor='k',label=f'{sp} ({len(gdf)} fields)')
    for r in gdf.itertuples(): ax.annotate(str(int(r.flags_review)),(r.lon,r.lat),ha='center',va='center',fontsize=8,color='white')
ax.set_xlabel('Longitude (WGS84)'); ax.set_ylabel('Latitude (WGS84)'); ax.legend(title='Geographic split',loc='upper right'); ax.set_ylim(top=30.6255)
ax.set_title('Field centroids; number = review flags (excl. suspected scene artefact)\nScreening signals only, not verified damage',fontsize=10); plt.tight_layout(); plt.savefig(f'{out}/figures/03_flags_by_field_map.png',dpi=150); plt.close()
# --- metrics
M=dict(source_sha256=hashlib.sha256(open(SRC615,'rb').read()).hexdigest(),rows=len(d),fields=int(d.field_id.nunique()),dates=int(d.date.nunique()),split_fields=d.groupby('split').field_id.nunique().to_dict(),split_rows=d.split.value_counts().to_dict(),
 rows_with_baseline=int(d.baseline_prior3.notna().sum()),train_residuals=int(len(tr)),residual_median=float(med),residual_MAD=float(mad),threshold=float(thr),flags=int(d.flag.sum()),
 flags_by_category=d[d.flag].flag_category.value_counts().to_dict(),flags_by_split=d[d.flag].split.value_counts().to_dict(),
 aot_flagged_mean=float(d[d.flag].aot_s2_mean.mean()),aot_all_mean=float(d.aot_s2_mean.mean()),
 flag_rate_after_gt10d_gap=float(d[d.long_gap&d.baseline_prior3.notna()].flag.mean()),flag_rate_overall=float(d[d.baseline_prior3.notna()].flag.mean()),
 may17=dq[dq.date=='2025-05-17'].iloc[0].to_dict(),second_highest_date_aot=float(dq.mean_aot_s2.nlargest(2).iloc[1]),
 bench=bench.round(5).to_dict('records'),contrast=diff.round(5).to_dict('records'),split_summary=sp_sum.round(5).to_dict('records'))
M['may17']={k:(str(v) if k=='date' else float(v)) for k,v in M['may17'].items() if k!='scene_qa_note'}
json.dump(M,open(f'{out}/verification/metrics.json','w'),indent=1,default=str)
d[['field_id','date']].assign(x=1)  # noqa
print(json.dumps({k:M[k] for k in ['flags','flags_by_category','flags_by_split','threshold','aot_flagged_mean','aot_all_mean','flag_rate_after_gt10d_gap','flag_rate_overall','may17','second_highest_date_aot']},indent=1,default=str))
print(bench.round(4).to_string()); print(diff.round(4).to_string()); print(sp_sum.round(3).to_string())
