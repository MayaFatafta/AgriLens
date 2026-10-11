# Data sources and attribution

Checked against the retained metadata and provider pages on 11 October 2026. The sample consists of derived field summaries. Cropping, quality screening, aggregation and feature engineering are AgriLens modifications. No provider endorses this project.

| Product | Actual use | Terms and attribution |
| --- | --- | --- |
| Copernicus Sentinel-2 L2A, 2025, via Microsoft Planetary Computer | NDVI/NDMI/EVI and quality-screened field histories | Free, full and open access under the [Sentinel legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice). Contains modified Copernicus Sentinel data (2025). [Collection](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a). |
| NASA EMIT L2A reflectance, 15 June 2025, NASA/EMIT/L2A/RFL | 14 field spectra, 232 retained complete wavelengths | NASA EMIT data have no restrictions on subsequent use, sale or redistribution, as stated in the [Earth Engine product catalogue](https://developers.google.com/earth-engine/datasets/catalog/NASA_EMIT_L2A_RFL). Credit Green, R. (2022), EMIT L2A Estimated Surface Reflectance and Uncertainty and Masks 60 m V001, NASA EOSDIS LP DAAC, [DOI](https://doi.org/10.5067/EMIT/EMITL2ARFL.001). |
| Fields of the World global predictions, 2024-2025 | Predicted field polygons and field identifiers | [Source Cooperative product](https://source.coop/ftw/global-data), CC BY 4.0. Credit Robinson et al. (2026), The first global agricultural field boundary map at 10 m resolution, arXiv:2605.11055. These are model-predicted units, not cadastral parcels. |
| Open-Meteo archive and air-quality APIs, including CAMS context | Modeled weather, dust/AOD and deep-layer soil moisture | [CC BY 4.0 data licence](https://open-meteo.com/en/licence). Credit Open-Meteo and the upstream CAMS/ECMWF providers indicated in the metadata. API service terms are separate from the data licence. |
| ESA WorldCover 2021 v200 | Historical land-cover context | [CC BY 4.0](https://esa-worldcover.org/en/data-access). © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. |
| MODIS MOD13Q1 v061 and NASA POWER | Retained supplementary context/metadata, not primary forecast features | NASA Earth-science open-data policy. Credit NASA LP DAAC / ORNL DAAC for MODIS and NASA POWER for meteorological context. See [MODIS product](https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset) and [POWER](https://power.larc.nasa.gov/). |
| EnMAP | Catalogue search metadata only | No EnMAP image data or spectra are bundled or claimed. Access/product terms remain with DLR. |

CC BY 4.0: https://creativecommons.org/licenses/by/4.0/ . Source records: `01_Sentinel2_original/provenance.json`, `10_Metadata/`, and `03_EMIT_hyperspectral/EMIT_S2_alignment_report.json`.

## Code, analysis and assistance
Team contributions: Maya (data and QA), Rand (modeling), Rama (validation), Nour (dashboard), Omar (documentation and presentation). This packaging update used ChatGPT assistance for notebook path repair, reproducibility checks, documentation and pitch preparation. Existing modeling and scientific results remain attributable to the team. Original third-party data retain their own terms. This document does not assign a new blanket software licence to team-owned code.
