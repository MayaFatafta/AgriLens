# AgriLens — Final Egyptian research figures (v1)

**Scope:** descriptive visualizations from the manually audited AgriLens Egyptian field-date and EMIT observations. This is an additional **figures release**; it does not change or overwrite the original dataset.

- 615 **real** Sentinel-2 field-date observations, 20 geographically audited fields, 33 field-observation dates (March–September 2025)
- 14 genuine EMIT-observed fields on June 15, 2025, with 232 complete wavelengths, compared with Sentinel-2 on June 16, 2025
- 9 high-priority **screening review records**; **0** independently verified crop-damage labels
- Environmental-model conditions are regionally shared per date, **not** field-specific exposures
- No synthetic series, future-dependent retrospective pattern annotations, or weak dust/drought labels are plotted as observed truth

## Eight included figures

| Name (PNG and SVG) | What the figure shows | Key warning |
| --- | --- | --- |
| `01_field_ndvi_heatmap` | Observed NDVI for 20 audited fields across 33 dates; geographic split and 9 high-priority proxy screens outlined | Markers are inspection priorities, not damage labels |
| `02_example_field_vegetation_and_dust` | Real time series for field `1664803`: NDVI, NDMI and regional modeled dust | Coincidence does not establish dust as cause |
| `03_regional_context_and_declines` | Date-level modeled dust, modeled soil moisture, and field-date vegetation-decline counts | Dust/moisture shared regionally on a date and are not independent per-field observations |
| `04_screening_categories_and_review_priority` | Exclusive screening categories and priority counts (419 none, 187 medium, 9 high) | The 196 review rows are proxies, not confirmed crop stress |
| `05_emit_hyperspectral_signatures` | Three actual EMIT field median reflectance spectra, quality gaps, shaded proposed Satellite 813 range | Wavelength-range overlap does not validate transfer to Satellite 813 |
| `06_emit_vs_sentinel2_ndvi` | Cross-sensor descriptive comparison on 14 fields | Different dates (1 day apart), resolution and aggregation; not instrument accuracy |
| `07_emit_coverage_and_selection_bias` | Eligible vs usable EMIT fields by geographic split and observed quality fraction | Training coverage is substantially unrepresentative: 3/9 fields usable |
| `08_temporal_qa_feature_availability` | Number of valid temporally QA-gated feature windows in each field split | Valid feature windows do not establish real-world classification validity |

Figures are high-resolution **PNG** (for notebooks, documents and slides) and **SVG** (vector, editable in supported programs). `FIGURES_OVERVIEW.jpg` shows thumbnails of all eight.

## Reproduce locally on Windows

Extract `AgriLens_Final_Figures_v1.zip` and `AgriLens_Integrated_Real_Datasets_v1_ReadyToUse.zip` into the same parent folder, or use the combined `AgriLens_Integrated_Real_Datasets_v1_With_Figures.zip` package.

From the parent directory run:

```powershell
.\.venv_clean\Scripts\python.exe `
  .\AgriLens_Final_Figures_v1\scripts\generate_agrilens_figures.py `
  --data-dir .\AgriLens_Integrated_Real_Datasets_v1\data `
  --out .\AgriLens_Final_Figures_v1\figures
```

Requires `pandas`, `numpy`, and `matplotlib` (present in the verified `.venv_clean`).

If using the combined ZIP, the figure script is stored in `AgriLens_Integrated_Real_Datasets_v1/scripts/` and figures are in `AgriLens_Integrated_Real_Datasets_v1/figures/`:

```powershell
.\.venv_clean\Scripts\python.exe `
  .\AgriLens_Integrated_Real_Datasets_v1\scripts\generate_agrilens_figures.py `
  --data-dir .\AgriLens_Integrated_Real_Datasets_v1\data `
  --out .\AgriLens_Integrated_Real_Datasets_v1\figures
```

## Scientific restrictions

The figures cannot be used to claim verified crop dust/drought labels, individual-field dust exposure, irrigation prescriptions, operational early warning, or dust-versus-drought classification accuracy. Regional modeled environmental indicators are contextual. The first figure plots NDVI at accepted observation dates; pale cells are unobserved field-date entries, not necessarily clouds.

The spatial/geographic bias of the EMIT field sample remains unresolved. Cross-sensor index differences are descriptive because EMIT and Sentinel-2 were acquired on different days and have different spatial resolution and processing. The 2025 field-date series has **33** dates; an earlier **34-date pixel-level** product is separate and its precise difference is awaiting date reconciliation.

No inputs were modified. Source data are the CSVs in `AgriLens_Integrated_Real_Datasets_v1/data/`.
