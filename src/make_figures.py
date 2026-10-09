"""Create static reproducible evidence figures from the generated split and scores."""
from pathlib import Path
import json
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import box

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
inv=pd.read_csv(ROOT/'outputs'/'sampling_frame_and_splits.csv',dtype={'field_id':str})
geom=gpd.read_file(ROOT/'inputs'/'ftw_aoi_fields_with_crosswalk.geojson').to_crs(32636)
geom.field_id=geom.field_id.astype('string')
g=geom.merge(inv[['field_id','split_group']],on='field_id',how='left',validate='one_to_one')
g['split_group']=g['split_group'].fillna('excluded_prior_QA')
pro=json.loads((ROOT/'inputs'/'provenance.json').read_text())
area=box(*pro['aoi']['bounds_utm_m'])
fig,ax=plt.subplots(figsize=(9,6))
g.plot(ax=ax,column='split_group',categorical=True,legend=True,linewidth=.6,edgecolor='0.35',alpha=.65,legend_kwds={'loc':'upper right'})
gpd.GeoSeries([area],crs=g.crs).boundary.plot(ax=ax,linewidth=1.4,edgecolor='black')
ax.set_title('AgriLens Egypt AOI: FTW predicted fields and geographical holdout')
ax.set_xlabel('UTM Easting (m)');ax.set_ylabel('UTM Northing (m)')
ax.set_aspect('equal');fig.tight_layout();fig.savefig(OUT/'spatial_sampling_frame.png',dpi=160);plt.close(fig)

rep=json.loads((ROOT/'outputs'/'regression_baseline_scores.json').read_text())
fig,ax=plt.subplots(figsize=(8,4.5))
names=['Train','Validation','Future + held-out test']
r=[rep[s]['ridge']['MAE'] for s in ['train','validation','test']]
p=[rep[s]['persistence']['MAE'] for s in ['train','validation','test']]
x=np.arange(3);w=.34
ax.bar(x-w/2,p,w,label='Persistence')
ax.bar(x+w/2,r,w,label='Ridge')
ax.set_xticks(x,names);ax.set_ylabel('MAE (NDVI units)')
ax.set_title('Next-observation NDVI: baseline comparison')
ax.legend();ax.grid(axis='y',alpha=.3)
fig.tight_layout();fig.savefig(OUT/'regression_baseline_comparison.png',dpi=160);plt.close(fig)
print('Wrote:',*[str(x) for x in OUT.glob('*.png')])
