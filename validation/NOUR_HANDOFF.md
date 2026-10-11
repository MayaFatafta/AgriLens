# Handoff to Nour — Visualization

From: Rama (Validation). Everything here is derived only from the team's audited 615-row table. Read `AgriLens_Validation_Report.md` for the evidence; this page tells you what to plot and how to word it.

## Use these files

| File | Use it for |
|---|---|
| `results/validated_anomalies_615.csv` | Main table, all 615 rows: NDVI, expected NDVI, residual, flag, `flag_category`, split, `lon`/`lat` (WGS84 field centroids) |
| `results/inspection_queue.csv` | The review list, already sorted: genuine `review` items first, `scene_artifact_suspect` last |
| `results/agrilens_validated_alerts.geojson` | Map points (`[lon, lat]`, WGS84), one per flag, with `flag_category` and a note |
| `results/field_geography.csv` | One row per field: split, area, lon/lat, flag counts |
| `results/date_scene_QA.csv` | Per-date AOT, SCL shares, regional mean NDVI, flags |
| `results/forecast_benchmark_with_CI.csv` | Model comparison with 95% intervals |
| `figures/` | Three finished figures (PNG) you can reuse or restyle |

## Rules for the demo

1. **Show 23 review-worthy flags as "inspect", never as damage.** The 36 flags split as: 15 review, 3 long-gap, 5 unclassified-pixel, 13 scene-artefact.
2. **Never plot `scene_artifact_suspect` flags as alerts.** They are all from 17 May (AOT 0.85, region-wide dip that rebounds). If you show them, use a grey "suspect scene" style and say so.
3. **Use the same colours for the splits everywhere:** train blue `#1b6ca8`, validation green `#3a9a5b`, test orange `#d0602e`.
4. **Forecast chart:** show intervals. Say "persistence is the reference"; do not present Ridge as better.
5. **Map:** use the `lon`/`lat` columns or the GeoJSON as given. They are field centroids for orientation, not field boundaries (polygons are in `01_Sentinel2_original/ftw_aoi_sampling_frame.geojson` of the full dataset).
6. **EMIT spectra:** train fields are under-represented (3 of 9 usable); mention this beside any spectral figure.

## Wording to put beside charts

- Flags: "Screening signal for human review. Not verified crop damage and not evidence of dust or drought as the cause."
- Scene artefact: "Suspected atmospheric scene effect (high aerosol load); not counted as an alert."
- Benchmark: "Next-observation NDVI forecast. Evaluated on 37 pairs from 5 held-out fields in one Nile Delta locality."
- Footer: "Dust or Drought? — exploratory screening; independent field verification required."

## Do not show

Any dust-vs-drought accuracy or classification score; yield, water-saving or irrigation claims; the earlier numbers (0.1151 threshold, 38 flags, MAE 0.0311).

