# EnMAP scene identified; imagery requires account access

The public DLR STAC search found this L2A scene covering the AOI:

**ENMAP01-____L2A-DT0000142619_20250720T092413Z_005_V010502_20250722T115947Z**

Acquisition: **20 July 2025, 09:24:13 UTC**. Catalog cloud cover: **0%**. Catalog coverage does not establish local per-pixel quality.

`selected_scene.json` contains the original scene footprint, processing metadata and asset download links. `metadata/enmap_search.json` records the area/date catalog response.

The image and XML download requests redirected to a DLR account login page. The returned HTML has been discarded. No hyperspectral imagery is included in this ZIP.

To obtain the real image:

1. Open the official data-access page: https://www.enmap.org/data_access/
2. Use your permitted EnMAP/DLR account in EOWEB or the EOC Geoservice.
3. Search by the exact scene ID above, or use the Egypt AOI and 20 July 2025.
4. Download the **L2A spectral image**, **metadata XML** and quality masks.
5. Keep all downloaded bands and their wavelengths/scale/nodata information. The catalog advertises a 224-band L2A image; verify the actual file metadata.
6. Clip the image to `aoi.geojson` at its native 30 m scale, then inspect cloud/haze/shadow and defective-pixel masks before spectral analysis.

Do not describe this package as an implemented hyperspectral pipeline. A single available scene supports spectral inspection; it does not supply a seasonal hyperspectral time series.

Data license: https://geoservice.dlr.de/resources/licenses/enmap/EnMAP-Data_License_v1_1.pdf
