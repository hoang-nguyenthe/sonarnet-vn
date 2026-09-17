# Maritime land exclusion

Source: [GSHHG 2.3.7](https://www.soest.hawaii.edu/pwessel/gshhg/), full-resolution L1 polygons, June 15 2017. The original license and notices accompany this derivative. Download `gshhg-shp-2.3.7.zip` from the source page into `data_external/gshhg/`; run `python scripts/build_land_mask.py` (requires shapely, pyproj, pyshp) to reproduce it. The compressed manifest records the source archive SHA-256.

Scope: 101–117°E, 5–25°N. This is physical shoreline data, not a territorial or administrative boundary. Inland waters enclosed by L1 polygons are excluded for this maritime use case. Other regions are explicitly unknown, not certified water.

Only a detection whose entire georeferenced bounding box lies more than 500 metres inside mapped land is removed. A conservative 500 m coastal band retains near-shore candidates for manual review. This is an engineering buffer, not a guaranteed accuracy estimate. Small islands, reclaimed land, shoreline change, SAR geolocation errors and radar false positives remain possible. The mask does not prove vessel presence, type or AIS identity.

Geometry is projected to a regional azimuthal-equidistant CRS for buffering before clipping; classification uses the original detailed geometry. Only the visual overlay is simplified. Map layer visibility never disables the filter. Raw detections remain in the source report and the evidence export records excluded detections and the mask version. The public app annotates the filtered output consistently in images, lists, maps and AIS demonstrations.
