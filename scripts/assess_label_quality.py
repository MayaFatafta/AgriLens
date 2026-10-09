"""Conservative acceptance gate for independent crop-stress annotations.

Use only AFTER field-level measurements, photos, irrigation or soil reports
are available and independently reviewed. No labels are derived from NDVI,
aerosols, dust models, or inferred stress proxies.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd

CLASSES = {'dust_related_damage', 'drought_related_damage', 'mixed_or_other_cause', 'no_confirmed_damage'}
NOT_EVIDENCE = {'ndvi', 'ndre', 'ndmi', 's2_dust', 'aod', 'modelled_soil_moisture', 'automatic_proxy'}


def assess(annotation_file, out_file, min_train_per_class=10, min_validation_per_class=5, min_test_per_class=5):
    a=pd.read_csv(annotation_file,keep_default_na=False)
    must={'field_id','field_split','verified_label','independent_evidence_type',
          'independent_evidence_reference','field_observation_date','reviewer','confidence','adjudicator','adjudication_status'}
    if not must.issubset(a.columns):
        raise ValueError(f'Annotation columns missing: {sorted(must-set(a.columns))}')
    if a.field_id.duplicated().any():
        raise ValueError('Duplicate field labels; one field/time target per row in this template')
    a['verified_label']=a.verified_label.str.strip()
    a['independent_evidence_type']=a.independent_evidence_type.str.strip().str.lower()
    for col in ['independent_evidence_reference','field_observation_date','reviewer','confidence','adjudicator','adjudication_status']:
        a[col]=a[col].str.strip()
    labelled=a[a.verified_label.isin(CLASSES)].copy()
    rejected=labelled[
        labelled['independent_evidence_type'].eq('') |
        labelled['independent_evidence_type'].isin(NOT_EVIDENCE) |
        labelled['independent_evidence_reference'].eq('') |
        labelled['field_observation_date'].eq('') |
        labelled['reviewer'].eq('') |
        labelled['confidence'].eq('') |
        labelled['adjudicator'].eq('') |
        labelled['adjudicator'].eq(labelled['reviewer']) |
        labelled['adjudication_status'].ne('approved')
    ].copy()
    valid=labelled[~labelled.index.isin(rejected.index)].copy()
    invalid_dates=pd.to_datetime(valid.field_observation_date,errors='coerce').isna()
    n_invalid_dates=int(invalid_dates.sum())
    valid=valid[~invalid_dates]
    class_per_split=(valid.groupby(['field_split','verified_label']).size().unstack(fill_value=0))
    class_per_split=class_per_split.reindex(index=['train','validation','test'],columns=sorted(CLASSES),fill_value=0)
    # An overall gate requires at least two verified classes and multiple independent examples per class.
    classes_present=sorted(valid.verified_label.unique().tolist())
    minima={'train':min_train_per_class,'validation':min_validation_per_class,'test':min_test_per_class}
    balanced=(len(classes_present)>=2 and all(
        int(class_per_split.loc[split,label])>=minimum
        for split,minimum in minima.items() for label in classes_present))
    out={'annotation_rows_with_two_reviewer_approval_metadata':int(len(valid)),
         'unverified_rows':int((~a.verified_label.isin(CLASSES)).sum()),
         'claimed_label_rows_missing_required_documentation_or_review':int(len(rejected)+n_invalid_dates),
         'claimed_approved_classes':classes_present,
         'class_counts_by_geographic_split':{s:{c:int(class_per_split.loc[s,c]) for c in class_per_split.columns}
                                            for s in class_per_split.index},
         'class_count_minimums_for_optional_experiment':minima,
         'metadata_and_class_count_gate_passed':bool(balanced),
         'warning':'Two-reviewer metadata checks and sample counts do NOT independently authenticate evidence or establish causal labels. Rama must inspect original evidence, adjudication, and independent events before any model.'}
    Path(out_file).parent.mkdir(parents=True,exist_ok=True)
    with open(out_file,'w') as f:json.dump(out,f,indent=2)
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--annotations',default='outputs/independent_annotation_template.csv')
    ap.add_argument('--out',default='outputs/label_validation_gate.json')
    p=ap.parse_args()
    print(json.dumps(assess(p.annotations,p.out),indent=2))
