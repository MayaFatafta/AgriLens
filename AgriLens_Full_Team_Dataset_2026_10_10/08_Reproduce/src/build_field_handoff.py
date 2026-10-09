#!/usr/bin/env python3
"""Create an auditable, field-disjoint AgriLens field/date exploratory dataset.

Uses REAL exported field summaries and daily environmental CSVs. Does NOT create
synthetic observations or dust/drought labels. Does NOT claim model validity.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = ["field_id", "date", "pixel_count", "ndvi_mean", "ndmi_mean", "evi_mean", "aot_s2_mean"]
ENV = ["date", "dust", "aerosol_optical_depth", "soil_moisture_28_to_100cm", "precip_48h", "wind_max_48h", "sm_change_7d", "sm_change_48h"]


def prepare(fields: pd.DataFrame, env: pd.DataFrame, *, quarantine_field="1665168", min_pixels=20, min_coverage=0.5, test_frac=0.30, seed=42):
    """Return accepted field-date observations, inventory, and metadata."""
    bad_cols=[x for x in FEATURES if x not in fields.columns]
    bad_env=[x for x in ENV if x not in env.columns]
    if bad_cols or bad_env:
        raise ValueError(f"Missing columns: fields={bad_cols}, environment={bad_env}")
    if not 0 < test_frac < 1:
        raise ValueError("test_frac must be between 0 and 1")
    if min_pixels < 1 or not (0 < min_coverage <= 1):
        raise ValueError("min_pixels>=1 and 0<min_coverage<=1 required")
    f=fields.copy()
    f["field_id"]=pd.to_numeric(f["field_id"],errors="raise").astype("Int64").astype("string")
    f["date"]=pd.to_datetime(f["date"],errors="raise").dt.normalize()
    e=env.copy()
    e["date"]=pd.to_datetime(e["date"],errors="raise").dt.normalize()
    if f.duplicated(["field_id","date"]).any():
        raise ValueError("Duplicate field/date in field_timeseries.csv")
    if e.duplicated("date").any():
        raise ValueError("Duplicate date in daily_env.csv")
    f["pixel_count"]=pd.to_numeric(f["pixel_count"],errors="raise")
    all_fields=int(f.field_id.nunique())
    # Robust approximation of the typical number of valid pixels in a field.
    denominator=f.groupby("field_id")["pixel_count"].transform(lambda x:float(x.quantile(0.90)))
    f["coverage_ratio_vs_p90"]=f["pixel_count"] / denominator.replace(0,np.nan)
    f["low_coverage"]=((f["pixel_count"] < min_pixels)|(f["coverage_ratio_vs_p90"] < min_coverage))
    f["quarantined_polygon"]=f.field_id.eq(str(quarantine_field)) if quarantine_field else False
    excluded=f[f.low_coverage|f.quarantined_polygon].copy()
    selected=f[~(f.low_coverage|f.quarantined_polygon)].copy()
    ids=sorted(selected.field_id.unique())
    if len(ids) < 4:
        raise ValueError(f"Only {len(ids)} eligible fields; cannot produce useful disjoint split")
    rng=np.random.default_rng(seed)
    permutation=rng.permutation(len(ids))
    n_test=min(len(ids)-2,max(2,int(math.ceil(len(ids)*test_frac))))
    heldout={ids[j] for j in permutation[:n_test]}
    selected["split"]=np.where(selected.field_id.isin(heldout),"test","train")
    selected=selected.sort_values(["field_id","date"]).reset_index(drop=True)
    df=selected.merge(e,on="date",how="left",validate="many_to_one",indicator=True)
    n_missing=int((df._merge!="both").sum())
    df=df.drop(columns="_merge")
    # Changes in field means, not unvalidated attribution labels.
    byfield=df.groupby("field_id",sort=False)
    df["ndvi_change_from_prev"]=df.ndvi_mean-byfield.ndvi_mean.shift(1)
    df["ndmi_change_from_prev"]=df.ndmi_mean-byfield.ndmi_mean.shift(1)
    df["days_since_prev"]=((df.date-byfield.date.shift(1)).dt.days)
    tr=set(df.loc[df.split=="train","field_id"])
    te=set(df.loc[df.split=="test","field_id"])
    assert not(tr&te), "field leakage"
    assert not df.duplicated(["field_id","date"]).any(), "duplicate field/date"
    per_field=(df.groupby(["field_id","split"],as_index=False)
                 .agg(n_observations=("date","size"),date_start=("date","min"),date_end=("date","max"),
                      typical_coverage=("coverage_ratio_vs_p90","median")))
    report={
        "source_files":["field_timeseries.csv","daily_env.csv"],
        "source_files_are_supplied_real_project_exports_not_independently_sensor_verified":True,
        "input_field_count":all_fields,
        "quarantine_field_id":str(quarantine_field) if quarantine_field else None,
        "quarantine_is_geometry_review_not_evidence_of_invalidity":True,
        "quarantine_reason":"Unusually large field footprint and disproportionate observations; field geometry unverified",
        "coverage_denominator":"within-field 90th percentile of clear pixel_count over all available dates",
        "min_clear_pixel_count":int(min_pixels),
        "min_coverage_fraction":float(min_coverage),
        "excluded_rows_total":int(len(excluded)),
        "excluded_low_coverage_rows":int(f.low_coverage.sum()),
        "quarantined_rows":int(f.quarantined_polygon.sum()),
        "input_field_date_rows":int(len(f)),
        "accepted_field_date_rows":int(len(df)),
        "eligible_fields":int(df.field_id.nunique()),
        "train_field_count":int(len(tr)),
        "test_field_count":int(len(te)),
        "train_rows":int((df.split=="train").sum()),
        "test_rows":int((df.split=="test").sum()),
        "overlapping_field_ids":sorted(tr&te),
        "missing_daily_env_dates":int(n_missing),
        "missing_values_by_col":{col:int(v) for col,v in df.isna().sum().items() if v},
        "date_min":str(df.date.min().date()), "date_max":str(df.date.max().date()),
        "split_seed":int(seed), "holdout_fraction_by_field":float(test_frac),
        "target_variable":"NONE: no independent dust/drought ground truth supplied",
        "limitations":[
          "This table is for descriptive temporal change screening and future independently-labeled modeling, not validated dust/drought classification.",
          "Fields in training and test are disjoint, but neighboring field proximity and shared observation dates remain; not a spatially buffered or temporally held-out test.",
          "Dust, AOD, meteorology and soil moisture are coarse regional model context repeated across many fields on a date; field-date rows are not independent atmosphere observations.",
          "Coverage is measured relative to observed p90 clear pixels, not a verified total field-polygon pixel count.",
          "FTW polygon geometry and field IDs, and ESA WorldCover land-cover mismatch require independent review.",
          "Region, mission/product metadata, provenance and source licensing still require verification from original manifests.",
          "EVI extremes in the full pixel table have not been investigated through this CSV-based procedure.",
        ],
    }
    return df,per_field,report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fields",type=Path,default=Path("field_timeseries.csv"))
    ap.add_argument("--env",type=Path,default=Path("daily_env.csv"))
    ap.add_argument("--out",type=Path,default=Path("field_handoff"))
    ap.add_argument("--quarantine-field",default="1665168")
    ap.add_argument("--min-pixels",type=int,default=20)
    ap.add_argument("--min-coverage",type=float,default=0.5)
    ap.add_argument("--test-fraction",type=float,default=0.30)
    ap.add_argument("--seed",type=int,default=42)
    args=ap.parse_args()
    fields=pd.read_csv(args.fields)
    env=pd.read_csv(args.env)
    df,inventory,report=prepare(fields,env,quarantine_field=args.quarantine_field,min_pixels=args.min_pixels,
                                 min_coverage=args.min_coverage,test_frac=args.test_fraction,seed=args.seed)
    args.out.mkdir(parents=True,exist_ok=True)
    df.to_csv(args.out/"field_date_analysis.csv",index=False,date_format="%Y-%m-%d",float_format="%.8g")
    inventory.to_csv(args.out/"field_split_inventory.csv",index=False,date_format="%Y-%m-%d",float_format="%.8g")
    (args.out/"field_qa_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("input_field_date_rows","accepted_field_date_rows","excluded_rows_total","eligible_fields","train_field_count","test_field_count","overlapping_field_ids","target_variable")},indent=2))
    print("Output:",args.out.resolve())

if __name__=="__main__":
    main()
