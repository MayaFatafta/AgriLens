# Corrected NDVI modeling module — release audit

**Module owner:** Rand (original code) / integrated fixes by review

**Version:** 1.2.0

The corrected code is `scripts/ndvi_anomaly_detection.py`. The original uploaded notes are preserved in `CODE_AUDIT_ORIGINAL.md`.

## Verified fixes

| Defect | Fix and test |
| --- | --- |
| Historical split misread | Prioritize official `field_split` over `historical_split_recorded`, disallow automatic historical fallback, verify 9/6/5; regression test with contradictory columns |
| May 17 raw alerts presented as crop reviews | Date-level quality note from independent validation; retain `anomaly_flag`, set `scene_qa_status`, `operational_review_candidate`, and hold priority; regression test |
| Empty model GeoJSON | Strict audited WGS84 centroid mapping from Rama's `field_geography.csv`; split consistency and unique fields verified; positive/negative coordinate tests |
| Optional modeled moisture absent from auto features | Support `soil_moisture_28_to_100cm` as a lagged predictor; note experimental change in outputs |
| Ambiguous negative phrasing | State positive magnitude below expected and separately report signed residual; regression test |
| Model/dashboard metric conflation | Both experiment results preserved separately and explicitly labeled in root README and dashboard |
| Hard-to-reproduce filenames | Correct `scripts/`, `tests/`, `docs/`, and `requirements-modeling.txt` with PowerShell runner |

## Current real-data run

- Official audited input: 615 field-date rows; 20 fields; 33 field observation dates.
- Split counts: 9 train, 6 validation, 5 test; **chosen column: `field_split`**.
- One-step scored pairs: 595, including 152 held-out test pairs.
- Model: Ridge(alpha=1.0), selected using validation. Test persistence MAE **0.029575**; selected Ridge test MAE **0.031036**.
- Training-only out-of-fold lower-tail residual cutoff: approximately **−0.09187**.
- **16** raw model flags; **5** on a suspect high-aerosol scene; **11** quality-screened review candidates.
- Mapped GeoJSON counts: 16 raw and 11 screened, from independently audited 20-field centroids.
- Deterministic synthetic regression suite: **13 passed**. Browser smoke check: desktop/mobile no JavaScript exceptions.

## Remaining limitations

No verified causal damage labels. Scene-QA overlay is retrospective; source quality assessments can draw on neighboring scene context. Satellite georeferencing is point centroids, not field polygons. Contextual modeled deep moisture is not observed irrigation. Selected Ridge has worse held-out test MAE than persistence. Dependencies in the uploaded requirements are not version-pinned. Experimental counts can change with dependency updates.

The 34 reported pixel-date acquisitions versus 33 retained field dates reflect a masked/unusable acquisition, documented by the dashboard; the difference must remain visible in provenance.
