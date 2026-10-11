# Final GitHub release — correction log

## 2026-10-11 — model integration correction

- Integrated the full audited team release, Rama's validation package, Rand's uploaded modeling files, and Nour's self-contained demo into one GitHub-ready directory.
- **Fixed wrong geographic split inference** using `field_split` rather than the historical two-way marker; added a regression test with both columns present.
- **Added retrospective scene-quality screening** to Rand's model: five raw flags on the 17 May 2025 suspect scene are held for image review; all raw flags are retained.
- **Added 20-field audited coordinate join** with one-to-one and geographic partition validation; exported raw and quality-screened WGS84 GeoJSON files.
- Added lagged modeled deep-layer soil moisture to accepted feature aliases and retested the full audited data. Results changed from the previous 15 raw flags to **16**; five suspect-scene holds leave **11** quality-screened review candidates.
- Fixed below-expected NDVI message sign conventions.
- Corrected Nour's dashboard copy to distinguish **14 positive / 9 negative** non-scene review observations and clarify that the dashboard and residual detector use different algorithms. No scientific data was replaced or silently merged.
- Created an executable Windows PowerShell entrypoint, updated documentation, preserved original modeling notes, and expanded deterministic tests from 7 to **13**.

### Reproducibility notes

Both original source packages have been copied byte-for-byte at file level. Rama's original validation hashes remain in `validation/SHA256_manifest.csv`. The original full-team manifest is retained as `10_Metadata/ORIGINAL_FULL_TEAM_SHA256_manifest.csv` (its source paths retain the original archive prefix). New outputs are reproducible from the included audited field-date source and validation QA/coordinate tables using `run_ndvi_modeling.ps1`.

**No claim of validated causal dust/drought performance or operational irrigation control is made.**
