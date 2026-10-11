# AgriLens Egyptian Data — Safe Additive Real-Observation Release v1

**Data product:** manual Egyptian Sentinel-2 field-date screening **plus** three derived temporal features. The quality-screened NASA EMIT release is retained as a separate, single-date hyperspectral layer. This release is an **additive derivative**, not a replacement for the manually audited source database.

**Scientific status:** exploratory vegetation-anomaly and environmental-context analysis. **0 independently verified dust-induced or drought-induced crop-damage labels.** Do not report real-world causal classification accuracy.

## Main files

| File | Rows | Purpose |
|---|---:|---|
| `data/agrilens_real_field_date_enhanced_615.csv` | 615 | Exact 54-column manual screening table + 3 imported, past/current v2 NDVI history features (57 columns). No other source field changed. |
| `data/agrilens_real_field_date_QA_gated_615.csv` | 615 | Same real records plus **three separately computed QA-gated features and three QA flags** (63 columns), recommended when examining anomalies. |
| `data/agrilens_retrospective_patterns_NOT_FOR_MODEL.csv` | 615 | Next-observation, future-dependent temporal descriptors. **Never use as prediction inputs or real dust/drought labels.** |
| `data/agrilens_manual_review_queue_196.csv` | 196 | Existing real-observation heuristic inspection queue, unchanged. |
| `data/agrilens_EMIT_master_20_fields.csv` | 20 | Full eligibility and missing-EMIT availability register. |
| `data/agrilens_EMIT_S2_usable_14_fields.csv` | 14 | Real June 2025 field-level EMIT/Sentinel-2 context (different acquisition dates). |
| `data/agrilens_EMIT_complete_spectra_3248.csv` | 3248 | 14 fields x 232 retained spectral bands, quality-screened from June 15, 2025. |
| `audit/verification_report.json` | — | Row/key/split, no-synthetic/label checks, QA feature coverage, source hashes and limitations. |
| `audit/EMIT_source_mask_verification.json` | — | Original EMIT quality-flag evidence for six excluded training fields. |
| `audit/EMIT_selection_bias_by_split.csv` | — | HSI availability imbalance by geographic split. |
| `audit/geographic_split_counts.csv` | 3 | Numbers of field-dates and distinct fields in geographic train/validation/test groups. |
| `SHA256_manifest.csv` | — | SHA-256 and sizes for included files (excluding the manifest itself). |
| `sources/agrilens_original_screening_615.csv` | 615 | **Unmodified** base manual-screening input. |
| `sources/agrilens_v2_real_tidy_source_615.csv` | 615 | v2 real-only derived input. Synthetic benchmark deliberately excluded. |
| `sources/AgriLens_Egypt_Manual_Release_v1.zip` | — | Original frozen EMIT release archive included for a self-contained rebuild. |

## QA-gated feature definitions

See `FEATURES_AND_LIMITATIONS.md` for exact rules. The original v2 features are retained with the `v2_` prefix to allow reproduction/comparison. The `qa_` features are deliberately separate instead of silently overwriting them.

**No source observations or original screening flags have been modified.** All 615 original field-date keys, 20 fields, 33 dates, and geographic split definitions remain unchanged. EMIT remains a single acquisition, not part of a repeated HSI series.

## Reproduce on Windows

From the extracted package folder, using your proven Python environment (pandas, numpy):

```powershell
.\.venv_clean\Scripts\python.exe .\AgriLens_Integrated_Real_Datasets_v1\scripts\build_integrated_release.py `
  --base .\AgriLens_Integrated_Real_Datasets_v1\sources\agrilens_original_screening_615.csv `
  --v2 .\AgriLens_Integrated_Real_Datasets_v1\sources\agrilens_v2_real_tidy_source_615.csv `
  --emit-zip .\AgriLens_Integrated_Real_Datasets_v1\sources\AgriLens_Egypt_Manual_Release_v1.zip `
  --out .\output\AgriLens_Integrated_Real_Datasets_rebuilt
```

The original frozen EMIT release ZIP is included under `sources/` for a full rebuild. To rebuild **only the 615-row enriched field-date table** without it, use the bundled `scripts/merge_verified_features.py` with `--base`, `--v2`, `--out` arguments (it outputs `enhanced_real_field_date_screening.csv`).

Check the verification report and manifest after extraction; do not treat software tests as external agronomic validation.

## Intended use

- **Maya:** data provenance, quality and geographic coverage audits.
- **Rand:** NDVI temporal-anomaly experimentation using QA-gated history features and independently held-out geographic fields; never use `NOT_FOR_MODEL` columns.
- **Rama:** quality-window and regional-environment validity assessment.
- **Nour:** plotting real vegetation histories plus separate single-date EMIT spectral signatures.
- **Omar:** research methods, reported limitations and the “Dust or Drought?” caveat.

**Irrigation advice:** screen fields for inspection and confirm local water status before changing irrigation. The dataset does not justify automatic irrigate/do-not-irrigate instructions.
