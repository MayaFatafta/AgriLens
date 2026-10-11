#!/usr/bin/env python3
"""AgriLens manually-audited Egyptian dataset: reproducible descriptive figures.

Usage:
 python generate_agrilens_figures.py --data-dir path/to/AgriLens_Integrated_Real_Datasets_v1/data --out path/to/figures

NO supervised damage labels or synthetic data are used.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

NAVY='#192B40'; BLUE='#3274A1'; GREEN='#188B7A'; ORANGE='#DE8F40'; RED='#C75F60'; GREY='#78899A'; LIGHT='#F2F5F7'; TEXT='#263746'
SPLIT_COL={'train':BLUE,'validation':GREEN,'test':ORANGE}


def style():
    plt.rcParams.update({
        'font.family':'DejaVu Sans', 'font.size':10.4,'axes.labelcolor':TEXT,
        'text.color':TEXT, 'axes.edgecolor':'#B9C6D0', 'xtick.color':'#40536A',
        'ytick.color':'#40536A','axes.titlecolor':NAVY,
        'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':0.8,
        'figure.facecolor':'white', 'axes.facecolor':'white',
        'savefig.facecolor':'white','savefig.dpi':200,
        'grid.color':'#E0E6EC','grid.alpha':0.8,'grid.linewidth':0.75,
    })


def save(fig, out, name):
    fig.savefig(out/f'{name}.png',bbox_inches='tight',dpi=220,pad_inches=.2)
    fig.savefig(out/f'{name}.svg',bbox_inches='tight',pad_inches=.2)
    plt.close(fig)


def heading(ax, title, subtitle=None):
    ax.set_title(title,loc='left',fontsize=15,fontweight='bold',pad=23)
    if subtitle:
        ax.text(0,1.015,subtitle,transform=ax.transAxes,fontsize=9,color=GREY,va='bottom')


def draw(d,s,e,m,out):
    dates=sorted(d.date.unique())
    assert len(d)==615 and d.field_id.nunique()==20 and len(dates)==33
    assert len(s)==3248 and s.field_id.nunique()==14 and s.wavelength_nm.nunique()==232
    assert len(m)==20 and len(e)==14
    assert set(e.field_id).issubset(set(d.field_id))
    assert not d.duplicated(['field_id','date']).any()

    # Figure 1: true field x date heatmap
    groups=[('train',d.loc[d.field_split=='train','field_id'].unique()),('validation',d.loc[d.field_split=='validation','field_id'].unique()),('test',d.loc[d.field_split=='test','field_id'].unique())]
    ordered=[int(fid) for split,ids in groups for fid in sorted(ids)]
    mat=d.pivot(index='field_id',columns='date',values='ndvi_mean').reindex(index=ordered,columns=dates)
    fig,ax=plt.subplots(figsize=(14.3,8.1))
    cmap=plt.get_cmap('YlGn').copy();cmap.set_bad('#E7EBEF')
    im=ax.imshow(np.ma.masked_invalid(mat.values),aspect='auto',interpolation='none',cmap=cmap,vmin=.15,vmax=.72)
    marks=d[d.screening_review_priority=='high']
    for _,r in marks.iterrows():
        ax.scatter(dates.index(r.date),ordered.index(int(r.field_id)),marker='s',s=85,facecolors='none',edgecolors=RED,linewidths=1.65)
    for sep in [len(groups[0][1])-.5,len(groups[0][1])+len(groups[1][1])-.5]: ax.axhline(sep,color='white',lw=3)
    for ix,(sn,ids) in enumerate(groups):
        lo=sum(len(groups[j][1]) for j in range(ix));hi=lo+len(ids)
        ax.plot([-1.08,-1.08],[lo-.4,hi-.6],color=SPLIT_COL[sn],lw=7,solid_capstyle='butt',clip_on=False)
        ax.text(-1.55,(lo+hi-1)/2,sn.upper(),rotation=90,va='center',ha='center',color=SPLIT_COL[sn],fontweight='bold',fontsize=8,clip_on=False)
    ax.set_yticks(range(len(ordered)));ax.set_yticklabels([str(x) for x in ordered],fontsize=8.4)
    inds=np.arange(0,len(dates),2);ax.set_xticks(inds);ax.set_xticklabels([pd.Timestamp(dates[i]).strftime('%d %b') for i in inds],rotation=45,ha='right',fontsize=8.4)
    ax.set_xlabel('2025 satellite acquisition date');ax.set_ylabel('Audited agricultural field ID')
    cb=fig.colorbar(im,ax=ax,pad=.01,shrink=.86);cb.set_label('Observed Sentinel-2 field-mean NDVI')
    heading(ax,'Vegetation condition across the audited agricultural fields','615 field-date observations  |  20 fields  |  33 observation dates')
    fig.text(.12,.03,'Outlined squares: 9 high-priority proxy review records. Pale cells: no accepted field-date record. These are NOT damage labels.',color=GREY,fontsize=9)
    fig.subplots_adjust(left=.14,bottom=.19,right=.95,top=.88)
    save(fig,out,'01_field_ndvi_heatmap')

    # Figure 2: field example real time series with independent axes
    fid=1664803
    t=d[d.field_id==fid].sort_values('date')
    fig,axs=plt.subplots(3,1,figsize=(12.1,9.6),sharex=True,gridspec_kw={'height_ratios':[1.3,1.0,.85]})
    axs[0].plot(t.date,t.ndvi_mean,color=GREEN,lw=2.2,marker='o',ms=4,label='Observed NDVI')
    bad=t[t.vegetation_decline_detected]
    axs[0].scatter(bad.date,bad.ndvi_mean,s=85,marker='v',color=RED,zorder=4,label='NDVI decline flag')
    axs[0].set_ylabel('NDVI');axs[0].set_ylim(max(0,t.ndvi_mean.min()-.09),min(1,t.ndvi_mean.max()+.1))
    axs[0].legend(loc='lower right',fontsize=9,frameon=False)
    axs[0].grid(axis='y')
    axs[1].plot(t.date,t.ndmi_mean,color=BLUE,lw=1.8,marker='o',ms=3.5)
    axs[1].axhline(0,color=GREY,lw=.8,ls='--')
    axs[1].set_ylabel('NDMI');axs[1].grid(axis='y')
    axs[2].plot(t.date,t.dust_max_48h,color=ORANGE,lw=1.8,marker='o',ms=3.7,label='Modeled regional dust (48 h max)')
    high=t[t.high_modeled_dust_context]
    axs[2].scatter(high.date,high.dust_max_48h,color=RED,s=35,zorder=5,label='Training-date high-context flag')
    axs[2].set_ylabel('Modeled dust\n(source units)');axs[2].grid(axis='y')
    axs[2].xaxis.set_major_locator(mdates.MonthLocator());axs[2].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    for ax in axs:ax.tick_params(axis='x',labelrotation=0)
    fig.suptitle(f'Field {fid}: observed vegetation and regional dust context',fontsize=15,fontweight='bold',x=.10,ha='left',y=.99,color=NAVY)
    fig.text(.1,.944,'Sentinel-2 NDVI / NDMI are field summaries; modeled dust is shared across fields by date.',fontsize=9,color=GREY)
    fig.text(.1,.025,'Declines and co-occurrences are inspection flags, not verified dust- or drought-induced crop damage.',fontsize=9,color=GREY)
    fig.tight_layout(rect=[.05,.055,.98,.93],h_pad=2.0)
    save(fig,out,'02_example_field_vegetation_and_dust')

    # Figure 3: dated event context
    daily=(d.groupby('date').agg(dust=('dust_max_48h','first'),soil=('soil_moisture_28_to_100cm','first'),
               decline=('vegetation_decline_detected','sum'),n_fields=('field_id','size'),dust_high=('high_modeled_dust_context','first'),
               soil_low=('low_modeled_deep_soil_moisture_context','first')).sort_index())
    assert (d.groupby('date').dust_max_48h.nunique()<=1).all()
    assert (d.groupby('date').soil_moisture_28_to_100cm.nunique()<=1).all()
    fig,axs=plt.subplots(3,1,figsize=(12.3,9.3),sharex=True)
    axs[0].plot(daily.index,daily.dust,color=ORANGE,lw=1.75,marker='o',ms=4)
    axs[0].scatter(daily.index[daily.dust_high],daily.dust[daily.dust_high],color=RED,marker='D',s=42,label='High modeled-dust context')
    axs[0].set_ylabel('Dust, 48 h max\n(source units)');axs[0].legend(loc='upper right',frameon=False,fontsize=9)
    axs[1].plot(daily.index,daily.soil,color=BLUE,lw=1.8,marker='o',ms=4)
    axs[1].scatter(daily.index[daily.soil_low],daily.soil[daily.soil_low],color=RED,marker='D',s=36,label='Low modeled-soil-moisture context')
    axs[1].set_ylabel('Deep soil moisture\n(source units)');axs[1].legend(loc='upper right',frameon=False,fontsize=9)
    axs[2].bar(daily.index,daily.decline,width=3.7,color=GREEN)
    axs[2].set_ylabel('Field-date\nNDVI declines');axs[2].set_ylim(0,max(3,daily.decline.max()+1))
    for ax in axs: ax.grid(axis='y');ax.set_axisbelow(True)
    axs[-1].xaxis.set_major_locator(mdates.MonthLocator());axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    axs[-1].set_xlabel('Satellite observation dates, 2025')
    fig.suptitle('Regional modeled environment vs observed field changes',x=.09,y=.99,ha='left',fontsize=15,fontweight='bold',color=NAVY)
    fig.text(.09,.948,'Same modeled value applies to every field on each date. Decline counts are field-date flags, not independent dust events.',color=GREY,fontsize=9)
    fig.text(.09,.023,'Date-level series is descriptive only; modeled soil moisture may poorly represent canal-irrigated fields.',fontsize=9,color=GREY)
    fig.tight_layout(rect=[.045,.055,.98,.94],h_pad=1.55)
    save(fig,out,'03_regional_context_and_declines')

    # Figure 4: screening summary, mutually exclusive categories and flag counts
    cats=d.screening_category.value_counts()
    cat_labels={
        'no_detected_screening_indicator':'No detected indicator',
        'low_modeled_moisture_context':'Low modeled-moisture context',
        'high_modeled_dust_exposure_context':'High modeled-dust context',
        'vegetation_decline_detected':'Vegetation decline',
        'insufficient_input_evidence':'Insufficient temporal evidence',
        'possible_moisture_stress_proxy':'Moisture-stress proxy',
        'vegetation_decline_with_moisture_context':'Decline + moisture context',
        'vegetation_decline_with_dust_context':'Decline + dust context',
        'multiple_stress_indicators':'Multiple proxy indicators'
    }
    cats=cats.loc[[k for k in cat_labels if k in cats.index]]
    fig,axs=plt.subplots(1,2,figsize=(14.2,6.8),gridspec_kw={'width_ratios':[1.75,1]})
    ypos=np.arange(len(cats))[::-1]
    colors=[GREY,BLUE,ORANGE,GREEN,GREY,BLUE,GREEN,ORANGE,RED]
    axs[0].barh(ypos,cats.values,color=colors[:len(cats)],height=.67)
    axs[0].set_yticks(ypos);axs[0].set_yticklabels([cat_labels[k] for k in cats.index],fontsize=9)
    axs[0].set_xlim(0,max(cats)*1.21)
    for pos,v in zip(ypos,cats.values):axs[0].text(v+3,pos,str(v),va='center',fontsize=9.3,fontweight='bold')
    axs[0].grid(axis='x');axs[0].set_axisbelow(True);axs[0].set_xlabel('Field-date records (exclusive categories)')
    priorities=d.screening_review_priority.value_counts().reindex(['none','medium','high'],fill_value=0)
    colors2=[GREY,BLUE,RED]
    bars=axs[1].bar(['None','Medium','High'],priorities.values,color=colors2,width=.65)
    for b,v in zip(bars,priorities.values): axs[1].text(b.get_x()+b.get_width()/2,v+6,str(v),ha='center',fontweight='bold')
    axs[1].set_ylim(0,max(priorities)*1.17);axs[1].set_ylabel('Field-date records')
    axs[1].grid(axis='y');axs[1].set_axisbelow(True)
    axs[1].set_title('Review priority',loc='left',color=NAVY,fontsize=13,fontweight='bold')
    fig.suptitle('What the rule-based field screening actually flags',x=.06,y=.99,ha='left',fontsize=15,fontweight='bold',color=NAVY)
    fig.text(.06,.935,'615 real field-date records | 30 vegetation-decline flags | 3 dust + decline co-occurrences | 0 verified damage labels',color=GREY,fontsize=9)
    fig.text(.06,.015,'Screening groups are mutually exclusive; separate binary indicator counts overlap and must not be summed.',color=GREY,fontsize=9)
    fig.tight_layout(rect=[.02,.04,.99,.91],w_pad=3)
    save(fig,out,'04_screening_categories_and_review_priority')

    # Figure 5: EMIT hyperspectral reflectance, break at discontinuities
    top=e.sort_values('emit_valid_pixel_count',ascending=False).head(3)
    fig,ax=plt.subplots(figsize=(13.2,6.7))
    for idx,(_,r) in enumerate(top.iterrows()):
        sub=s[s.field_id==r.field_id].sort_values('wavelength_nm')
        wl=sub.wavelength_nm.to_numpy();refl=sub.reflectance_median.to_numpy()
        xx=[];yy=[]
        for j,(a,b) in enumerate(zip(wl,refl)):
            if j and a-wl[j-1]>23: xx.append(np.nan); yy.append(np.nan)
            xx.append(a); yy.append(b)
        ax.plot(xx,yy,lw=2.1,color=[BLUE,GREEN,ORANGE][idx],label=f"Field {int(r.field_id)}  (n={int(r.emit_valid_pixel_count)} EMIT pixels)")
    ax.axvspan(400,1700,color='#DBEAFE',alpha=.35,label='813 published spectral range (400–1700 nm)')
    ax.axvspan(680,760,color='#E2F0DD',alpha=.4)
    ax.text(723,.12,'Red edge',ha='center',fontsize=9,color=GREEN,rotation=90)
    ax.set_xlabel('EMIT wavelength center (nm)');ax.set_ylabel('Median surface reflectance')
    ax.set_xlim(385,2470);ax.grid(axis='y');ax.set_axisbelow(True)
    ax.legend(loc='upper left',fontsize=9,frameon=False)
    heading(ax,'Real Egyptian EMIT field spectral signatures','15 June 2025  |  232 retained wavelengths  |  Missing / excluded spectral gaps are not interpolated')
    fig.text(.12,.015,'The shaded range indicates potential 813 wavelength coverage, NOT matched instrument response bands or validated transfer.',fontsize=9,color=GREY)
    fig.tight_layout(rect=[.05,.045,.98,.92])
    save(fig,out,'05_emit_hyperspectral_signatures')

    # Figure 6: EMIT vs S2 NDVI scatter
    fig,ax=plt.subplots(figsize=(9.5,8.3))
    for sp,subset in e.groupby('field_split',sort=False):
        ax.scatter(subset.s2_ndvi_mean,subset.emit_ndvi_median, s=45+subset.emit_valid_pixel_count*2.8,
                   c=SPLIT_COL[sp],edgecolors='white',lw=1.0,alpha=.91,label=f'{sp.title()} ({len(subset)} fields)')
    lims=[min(e.s2_ndvi_mean.min(),e.emit_ndvi_median.min())-.045,max(e.s2_ndvi_mean.max(),e.emit_ndvi_median.max())+.045]
    ax.plot(lims,lims,color=GREY,ls='--',lw=1.3,label='1:1 reference')
    ax.set_xlim(lims);ax.set_ylim(lims);ax.set_aspect('equal',adjustable='box')
    ax.grid(alpha=.65);ax.set_axisbelow(True)
    r=float(np.corrcoef(e.s2_ndvi_mean,e.emit_ndvi_median)[0,1]);mae=float(np.abs(e.s2_ndvi_mean-e.emit_ndvi_median).mean())
    ax.text(.03,.97,f'Fields: {len(e)}   |   Pearson r = {r:.3f}\nMean absolute cross-sensor difference = {mae:.3f}',ha='left',va='top',transform=ax.transAxes,
            fontsize=10,color=NAVY,bbox=dict(boxstyle='round,pad=0.55',facecolor=LIGHT,edgecolor='none'))
    ax.set_xlabel('Sentinel-2 NDVI mean (16 June)');ax.set_ylabel('EMIT NDVI median (15 June)')
    ax.legend(loc='lower right',frameon=True,facecolor='white',fontsize=9)
    heading(ax,'EMIT versus Sentinel-2 vegetation indices','Different sensors, different pixel sizes, dates one day apart  |  Marker size reflects valid EMIT pixels')
    fig.text(.1,.015,'This is descriptive cross-sensor agreement, NOT retrieval accuracy or verified crop-condition assessment.',color=GREY,fontsize=9)
    fig.tight_layout(rect=[.035,.045,.98,.92])
    save(fig,out,'06_emit_vs_sentinel2_ndvi')

    # Figure 7: EMIT geographic split coverage explicit bias
    counts=m.groupby('field_split').agg(eligible=('field_id','size'),usable=('emit_valid_pixel_count',lambda x:(x>=3).sum()))
    counts=counts.reindex(['train','validation','test'])
    fig,axs=plt.subplots(1,2,figsize=(12.6,5.8),gridspec_kw={'width_ratios':[1.15,1.25]})
    x=np.arange(3)
    axs[0].bar(x,counts.eligible,color='#D7DFE7',label='Eligible',width=.65)
    axs[0].bar(x,counts.usable,color=[SPLIT_COL[sp] for sp in counts.index],label='Usable EMIT',width=.65)
    for xi,(a,b) in enumerate(zip(counts.eligible,counts.usable)):
        axs[0].text(xi,a+.25,f'{int(b)}/{int(a)}',ha='center',fontweight='bold',fontsize=11)
    axs[0].set_xticks(x);axs[0].set_xticklabels(['Train','Validation','Test']);axs[0].set_ylim(0,11)
    axs[0].set_ylabel('Agricultural field count');axs[0].grid(axis='y');axs[0].set_axisbelow(True)
    axs[0].legend(loc='upper right',fontsize=9,frameon=False)
    axs[0].set_title('EMIT availability by geographic split',loc='left',fontsize=12,fontweight='bold')
    # per-field 60m QA coverage, 0 for 6 omitted
    mm=m.sort_values(['field_split','emit_quality_coverage_fraction'],key=lambda col:col.map({'train':0,'validation':1,'test':2}) if col.name=='field_split' else col)
    y=np.arange(len(mm))[::-1]
    axs[1].barh(y,mm.emit_quality_coverage_fraction*100,color=[SPLIT_COL[x] if float(q)>0 else '#CFD8E1' for x,q in zip(mm.field_split,mm.emit_quality_coverage_fraction)],height=.75)
    axs[1].set_yticks(y);axs[1].set_yticklabels([str(x) for x in mm.field_id],fontsize=8)
    axs[1].set_xlim(0,105);axs[1].set_xlabel('Valid EMIT grid centers in field (%)')
    axs[1].grid(axis='x');axs[1].set_axisbelow(True)
    axs[1].set_title('Observed field-level quality coverage',loc='left',fontsize=12,fontweight='bold')
    fig.suptitle('Hyperspectral sampling bias is concentrated in training fields',x=.06,y=.985,ha='left',fontsize=15,fontweight='bold',color=NAVY)
    fig.text(.06,.935,'6 / 9 training fields lack usable spectra; they remain in the master availability register (not imputed).',color=GREY,fontsize=9)
    fig.text(.06,.016,'Field bars show 60 m quality coverage; a nonzero coverage fraction is not necessarily robust training representation.',fontsize=9,color=GREY)
    fig.tight_layout(rect=[.045,.04,.99,.9],w_pad=3)
    save(fig,out,'07_emit_coverage_and_selection_bias')

    # Figure 8: rolling quality gate and viable features by split
    fig,ax=plt.subplots(figsize=(11.4,6))
    by=d.groupby('field_split').agg(total=('field_id','size'), temporal=('qa_temporal_pair_ok','sum'),
                                    trend3=('qa_window3_ok','sum'),median5=('qa_window_prev5_ok','sum')).reindex(['train','validation','test'])
    bars_cols=['#B9C6D0',GREEN,BLUE,ORANGE]
    xx=np.arange(len(by));wid=.19
    for j,(col,name) in enumerate([('total','Records'),('temporal','Usable adjacent pair'),('trend3','3-point history'),('median5','5-point history')]):
        b=ax.bar(xx+(j-1.5)*wid,by[col].values,width=wid,color=bars_cols[j],label=name)
        for rect,k in zip(b,by[col]):ax.text(rect.get_x()+rect.get_width()/2,rect.get_height()+3,str(int(k)),ha='center',fontsize=8)
    ax.set_xticks(xx);ax.set_xticklabels(['Train','Validation','Test']);ax.set_ylabel('Field-date records')
    ax.set_ylim(0,max(by.total)*1.17);ax.grid(axis='y');ax.set_axisbelow(True)
    ax.legend(loc='upper right',frameon=False,ncol=2,fontsize=9)
    heading(ax,'QA-gated temporal feature availability','Only prior observations are used  |  History windows enforce the configured maximum gap')
    fig.text(.11,.012,'Historical missingness is preserved as missing; the original 615 rows and geographic splits remain unchanged.',fontsize=9,color=GREY)
    fig.tight_layout(rect=[.055,.045,.99,.91])
    save(fig,out,'08_temporal_qa_feature_availability')

    return {
        'source':'AgriLens_Integrated_Real_Datasets_v1',
        'real_field_date_records':int(len(d)), 'unique_fields':int(d.field_id.nunique()),'unique_dates':int(d.date.nunique()),
        'source_em_it_scene':'EMIT_L2A_RFL_001_20250615T113555_2516607_021',
        'hyperspectral_fields':int(e.field_id.nunique()),'wavelength_count':int(s.wavelength_nm.nunique()),
        'spectral_records':int(len(s)),
        'screening_decline_count':int(d.vegetation_decline_detected.sum()),
        'screening_dust_decline_count':int(d.dust_and_vegetation_decline_cooccurrence.sum()),
        'screening_moisture_decline_count':int(d.moisture_and_vegetation_decline_cooccurrence.sum()),
        'high_priority_review_records':int((d.screening_review_priority=='high').sum()),
        'verified_damage_labels':int(d.damage_label_verified.sum()),
        'flags_regional_by_date':bool((d.groupby('date').dust_max_48h.nunique()<=1).all()),
        'figure_count':8,
        'cautions':['All screening outputs are noncausal proxies','EMIT and S2 are different dates, resolutions and spectral response functions',
         'Modeled environmental values do not vary across fields on the same date','EMIT missingness concentrates in training fields',
         'Retrospective labels and semi-synthetic data were not used to generate these plots']
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',type=Path,required=True,help='Integrated AgriLens real release data directory')
    p.add_argument('--out',type=Path,required=True,help='PNG/SVG output folder')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True);style()
    d=pd.read_csv(args.data_dir/'agrilens_real_field_date_QA_gated_615.csv',parse_dates=['date'])
    s=pd.read_csv(args.data_dir/'agrilens_EMIT_complete_spectra_3248.csv')
    e=pd.read_csv(args.data_dir/'agrilens_EMIT_S2_usable_14_fields.csv')
    m=pd.read_csv(args.data_dir/'agrilens_EMIT_master_20_fields.csv')
    report=draw(d,s,e,m,args.out)
    (args.out.parent/'audit'/'figure_data_verification.json').parent.mkdir(parents=True,exist_ok=True)
    (args.out.parent/'audit'/'figure_data_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
