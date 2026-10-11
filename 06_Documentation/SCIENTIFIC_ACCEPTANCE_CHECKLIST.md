# Acceptance checklist for Egypt EnMAP hyperspectral integration

**Never mark the following as verified using STAC metadata, quicklooks, or a synthetic code test alone.**

## Acquisition

- [x] AOI chosen and preserved: Egypt Nile Delta, 9 km², EPSG:32636.
- [x] DLR cached catalog search identifies scene `DT0000142619`, tile `005`, L2A, 2025-07-20.
- [x] Scene advertised as covering 100% of AOI in cached STAC geometry.
- [ ] Original EnMAP image COG downloaded and file signature inspected.
- [ ] Original EnMAP metadata XML downloaded and parsed.
- [ ] Cloud, cloud-shadow, haze, classes, defective-pixel mask downloaded.
- [ ] Optional cirrus/snow/test-flags checked if delivered.
- [ ] Validate official source checksum/signature when DLR supplies one; store digest and asset provenance.

## Per-pixel data QA

- [ ] Raster CRS and UTM bounds verified against 9 km² AOI (>= 99% geometry coverage).
- [ ] Spectral TIFF band count matches actual XML bandCharacterisation.
- [ ] Reflectance gain/offset taken from XML or authoritative TIFF metadata (no guessed scale).
- [ ] Wavelength band centers and red-edge/SWIR channels confirmed.
- [ ] AOI no-data, cloud, cloud shadow, haze, class and defective flags mapped and documented.
- [ ] Valid spectral pixels retained and summarized at native 30m grid.
- [ ] Remaining unusual spectral channels rejected/flagged after reviewing spectra.
- [ ] Field-level medians derived only from independently audited candidate polygons, not merged field 1665168.

## Integration and claims

- [x] Accepted Sentinel-2 observation on 2025-07-19 identified from audited field table.
- [ ] EnMAP field-IDs matched to actual Sentinel-2 field-IDs from the same locations.
- [ ] Spatial sampling effects (20m vs 30m), 1-day offset and bandpass differences reported.
- [ ] Any inferred stress label supported independently of dust / NDVI measurements.
- [ ] PoC notebook reports actual measured valid pixel counts and provenance.
- [ ] Satellite 813 is called target future sensor, not source of this imagery.

Until these unchecked items are completed, label the Egypt hyperspectral output **planned/awaiting downloaded imagery**, not validated.
