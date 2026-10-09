# AgriLens — Verified FTW 2025 boundary geometry audit

**Input**: uploaded `2025_N30E030.parquet` (72,778,738 bytes); `dataset.parquet`; `provenance.json`.
**AOI**: 3 × 3 km (900 ha), UTM EPSG:32636, centered at 30.25° E, 30.63° N, **Egypt**.

## Method

1. Read the uploaded Parquet footer and GeoParquet metadata. It identifies **364,693 predicted polygons**, WKB Polygon geometry in WGS84, 3 row groups, and source fields: `time`, `label`, `confidence_mean`, `confidence_median`, `confidence_min`, `geometry`, `chunk_id`.
2. The file **has no persistent `id` or `field_id` column**. We therefore decoded the actual Snappy-compressed polygon geometries and cropped them to the projected 3 × 3 km AOI; no field ID was assumed from the tile.
3. Decoded the necessary `x_utm`, `y_utm`, `field_id` columns from the uploaded AgriLens dataset's ZSTD/RLE-dictionary Parquet storage; consolidated its 707,580 observations to **22,500 unique coordinate pairs**.
4. Spatially joined all 22,500 pixel centers to the tile polygons and constructed a one-to-one crosswalk from the existing AgriLens IDs to tile polygon positions. Native `confidence_mean` values were decoded from the source tile, without interpreting them as probabilities.

## Verified results

| Property | Result |
| --- | ---: |
| FTW polygons in complete 1° source tile | 364,693 |
| FTW polygons intersecting AOI | 32 |
| FTW polygons matched to existing AgriLens field IDs | 31 |
| Tiny AOI polygons without a corresponding pixel center/AgriLens field ID | 1 |
| Unique Sentinel-2 pixel centers checked | 22,500 |
| Pixel centers with exactly one original field ID | 19,579 |
| Pixel centers within a tile polygon | 19,579 |
| Original vs uploaded tile *field membership* mismatches | **0** |
| Pixels intersecting multiple matched FTW polygons | **0** |
| Existing field 1665168 → temporary tile polygon | `tile_row_113314` |
| Pixel centers assigned to Field 1665168 | 15,984 |
| Field 1665168 matched to that single FTW polygon | **15,984 / 15,984** |
| Field 1665168 polygon area inside AOI | **639.871634 ha** |
| Field 1665168 polygon total area outside and inside AOI | **13,196.884883 ha = 131.968849 km²** |
| Fraction of 900-ha AOI occupied by the largest polygon | **71.10%** |
| Next-largest polygon clipped inside AOI | 21.935892 ha |
| Raw tile `confidence_mean` for that large polygon | 0.542562 (native scale, not a verified probability) |

## Scientific interpretation

- **The huge field is not a broken spatial join.** Its original 15,984 pixel assignments agree perfectly with the uploaded FTW polygon; the polygon's 639.87-ha clipped area agrees with 15,984 × 400 m² = 639.36 ha to within about 0.51 ha, a reasonable center-based rasterization difference.
- **The field-polygon model likely merged many real fields or land units.** The full connected polygon is 132 km², far too large to accept without visual inspection as one crop management unit in this Nile Delta site. The map visibly shows fine internal channels/field-like subdivisions within this polygon; vector geometry by itself cannot independently establish the correct subdivision or crop use.
- Accordingly, **exclude Field 1665168 from field-level training, testing, and individual-farm examples** until corrected subdivisions or ground truth are available. The existing 23-field corrected handoff already quarantines it.
- Do not interpret this as a real 639-ha farm or legal parcel. FTW boundaries are model-generated remote-sensing units, not cadastral ground truth.
- Original spatial-block split still leaks field IDs between train/test. Use previously prepared field-disjoint split for field-level work; this geometry audit does not repair the old `split` column.
- The tile contains 32 intersecting polygons vs. 31 assigned field IDs because one small polygon contains no 20-m pixel center in the observation grid. This is **not** necessarily a field ID mismatch.
- `confidence_mean` is **native tile metadata** and must not be presented as an empirically validated accuracy probability.

## Deliverables

- `ftw_aoi_fields_with_crosswalk.geojson` — all 32 verified AOI-intersecting polygons; 31 have the original AgriLens field ID added by coordinate match.
- `field_1665168_verified_geometry.geojson` — the giant polygon clipped to the AOI, with its original AgriLens field ID joined.
- `old_field_to_tile_spatial_crosswalk.csv` — pixel counts linking original IDs to the uploaded tile's row-number identifiers.
- `all_field_polygon_areas.csv` — each polygon's full/clipped area and field assignment.
- `field_geometry_alignment_report.json` — machine-readable agreement statistics.
- `FTW_AOI_geometry_preview.png` — vector-only visualization; no optical base image.

## Implications for project narrative

Maya's field geometry check is **finished** for alignment and area. It **does not** verify agronomic field boundaries with independent reference imagery. Describe Field 1665168 as a *predicted merged field region*, not a single farm. Focus the PoC on smaller field polygons with adequate observation coverage, and keep all dust/drought interpretations as candidate anomalies rather than ground-truth diagnoses.
