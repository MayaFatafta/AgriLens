from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'inputs'; F=ROOT/'figures'
F.mkdir(exist_ok=True)
a=pd.read_csv(P/'egypt_hsi_s2_usable_fields.csv')
s=pd.read_csv(P/'egypt_hsi_complete_spectra.csv')
assert len(a)==14 and a.field_id.nunique()==14
assert len(s)==3248 and s.wavelength_nm.nunique()==232
assert not s.reflectance_median.isna().any()
assert s.duplicated(['field_id','wavelength_nm']).sum()==0
assert set(s.field_id)==set(a.field_id)
print('QA PASSED: 14 fields, 232 wavelengths, 3248 records, no missing values or duplicate pairs')
fig,ax=plt.subplots(figsize=(11,5.7))
for row in a.nlargest(3,'emit_valid_pixel_count').itertuples():
 d=s[s.field_id==row.field_id].sort_values('wavelength_nm')
 x=d.wavelength_nm.to_numpy();y=d.reflectance_median.to_numpy()
 for idx in np.where(np.diff(x)>20)[0][::-1]:
  x=np.insert(x,idx+1,np.nan);y=np.insert(y,idx+1,np.nan)
 ax.plot(x,y,label=f'FTW field {row.field_id} (n={row.emit_valid_pixel_count})')
ax.set(xlabel='Wavelength (nm)',ylabel='Median surface reflectance',title='AgriLens Egypt | EMIT field spectra (15 June 2025)')
ax.grid(alpha=.25);ax.legend(fontsize=9)
fig.text(.5,.01,'Line breaks indicate filtered atmospheric / no-data wavelength intervals; crop status unknown.',ha='center',fontsize=8)
fig.tight_layout(rect=(0,.035,1,1));fig.savefig(F/'egypt_field_spectral_signatures_corrected.png',dpi=175);plt.close(fig)
fig,ax=plt.subplots(figsize=(7.8,6.9))
for split,g in a.groupby('field_split'):
 ax.scatter(g.s2_ndvi_mean,g.emit_ndvi_median,label=f'{split} (n={len(g)})',s=58)
lo=min(a.s2_ndvi_mean.min(),a.emit_ndvi_median.min())-.04
hi=max(a.s2_ndvi_mean.max(),a.emit_ndvi_median.max())+.04
ax.plot([lo,hi],[lo,hi],'--',lw=1,label='1:1 reference (not calibrated)')
for row in a.itertuples():
 if row.emit_valid_pixel_count<5 or row.emit_quality_coverage_fraction<.5:
  ax.annotate(str(row.field_id),(row.s2_ndvi_mean,row.emit_ndvi_median),xytext=(5,5),textcoords='offset points',fontsize=8)
ax.set(xlim=(lo,hi),ylim=(lo,hi),xlabel='Sentinel-2 field mean NDVI | 16 Jun 2025',ylabel='EMIT field median NDVI | 15 Jun 2025',title='AgriLens Egypt | Same-field, one-day-apart NDVI')
ax.set_aspect('equal',adjustable='box');ax.grid(alpha=.25);ax.legend(loc='upper left',fontsize=9)
fig.text(.5,.015,'Exploratory: 60 m vs 20 m; field median vs mean; different dates. Labels flag low-coverage fields.',ha='center',fontsize=8)
fig.tight_layout(rect=(0,.04,1,1));fig.savefig(F/'egypt_emit_vs_s2_ndvi_audited.png',dpi=175);plt.close(fig)
print('Plots refreshed under',F)
