# Result interpretation for the AgriLens PoC

## Completed empirical measurement (uploaded Tanager-derived medians)

- Input spectral rows: **361**; complete rows after excluding 4 wavelengths with both medians unavailable: **357**.
- The interpolation baseline takes reflectance only from Tanager wavelength bands nearest **665, 705, 740, 783, 842, 865 nm**; it linearly reconstructs the dense red-edge interval 680–800 nm.
- In the **higher-NDVI group median** (180 selected pixels), the dense-curve reconstruction RMSE was **0.02065 reflectance units**.
- In the **lower-NDVI group median** (180 selected pixels), the corresponding RMSE was **0.01346 reflectance units**.
- This quantifies how much the **center-sampled sparse approximation** missed in **these two observed median curves**, not how much prediction improves, and not how actual Sentinel-2 imagery performs.
- In the original processing report, the high-/low-group red-edge maximum-gradient locations are **725.96** and **715.94 nm**, respectively. Because grouping is defined by NDVI and only two median curves are available, this difference is descriptive only; no group-independent significance or disease interpretation is possible.

## Outstanding measurements

1. **Per-pixel spectral reconstruction error**: command ready; not executed in the sandbox because the ~1.05 GB real HDF5 is only on the user's Windows machine.
2. **Actual scene hash and publisher identity**: report and Planet tutorial metadata agree in shape/CRS; publisher checksum not available, so no byte-level independent authentication.
3. **True multispectral vs hyperspectral crop-stress model evaluation**: blocked until independent field crop-stress labels and a properly convolved sparse-band baseline are obtained.
4. **Satellite 813-specific evaluation**: blocked by incubator-only product access; no 813 imagery processed.

## Slide-safe text

> Using publicly released Tanager-1 hyperspectral reflectance, AgriLens extracted vegetation-index maps and vegetation spectral signatures. In an exploratory red-edge analysis, interpolating six sparse center-wavelength samples did not reproduce the full spectral curves (median-curve RMSE: 0.02065 and 0.01346 reflectance units for two NDVI-defined groups). This documents extra measured spectral structure, not proven improvement in crop-stress diagnosis. Satellite 813 integration is a future objective conditional on authorized imagery access.
