# Handoff to Nour / Rand / Rama / Omar

## Artifact status

- Code and independent standalone notebook are implemented and software-tested.
- Source real Tanager agricultural scene (Brazil) and exact public HDF5 URL are documented.
- The real image HDF5 has **not** been downloaded or processed in the current execution environment.
- Unit tests and notebook smoke test ran using explicitly **synthetic temporary HDF5 fixtures**. Those measurements must not appear in PoC results.

## Maya (Data)

1. On a networked Windows computer or Colab, download the **orthorectified surface-reflectance** HDF5 with the command in README.
2. Run `inspect` and `process` (do not use top-of-atmosphere radiance).
3. Verify `processing_report.json`: finite wavelength band axis, nonzero valid mask fraction, HDF5 scene identity and appropriate spectra.
4. Hand the actual 4 files in `output/tanager_brazil/` to Nour and Rama and retain source URL, scene ID and open-data license.

## Rand (Model)

Use the spectral signatures as **unsupervised descriptive features** or create a fair on-scene comparison against a small set of broadband indices. Do **not** report classification accuracy without independent labels, or claim the Egypt 2025 NDVI regression was trained with this Brazil scene.

## Rama (Validation)

Inspect figure for physically plausible vegetation curves (red absorption and NIR rise), cloudy pixels and artifacts. Cross-check that the two curves are *high versus low NDVI sampled pixel groups*, not known healthy/diseased crops. Flag any uncertain or failing observations.

## Nour (Integration lead)

Embed a figure and band/quality report in the final AgriLens notebook only after the real HDF5 run. Provide clear section headings:
- **Egypt study**: multispectral Sentinel-2 2025 historical analysis.
- **Brazil hyperspectral demonstration**: Tanager-1 1 May 2025 spectral detail.
- **Future 813 adaptation**: planned after access and sensor-specific validation.

The module does not implicitly merge the two study areas or add new targets to the regression CSV.

## Omar (Submission)

Cite Planet Labs PBC, the open agriculture STAC collection and scene ID. Describe limitations and permissions clearly. The repository should include code/notebook, a manifest and permitted derived examples, **not** unreviewed multi-GB raw data.
