# Vietnam maritime reference — display context only

This is a selected subset of the [Marine Regions Maritime Boundaries v12](https://doi.org/10.14284/632), published by Flanders Marine Institute (VLIZ) on 25 October 2023. It is **not an official Vietnamese legal-boundary dataset**.

## Files and reproducibility

- `vietnam_eez.geojson`: unmodified source geometry and attributes for MRGID 8484, “Vietnamese Exclusive Economic Zone”.
- `vietnam_boundary_lines.geojson`: associated source line segments. Keep `line_type`, source URLs, and dates; different line types have different meanings.
- `metadata.json`: request URLs, retrieval time, hashes, coordinate validation, citation, and display limitations.
- `fetch_reference.py`: regenerate with `python3 assets/maritime_reference/fetch_reference.py` (requires Shapely). No account is required.

Coordinates are longitude/latitude in WGS84 (EPSG:4326). The generator verifies the expected region and identity before replacing files. Source geometry is not hand-drawn or expanded.

**Geometry QA:** the retrieved source polygon has a self-intersection. It is retained unchanged as a provenance record, not a spatial-classification input. All 14 source boundary-line geometries passed validity checks. Prefer the approximately 96 KB line file for display (versus approximately 956 KB polygon); exclude `Straight baseline` from the outer-reference overlay. Keep the other line types in popups. Metadata records the exact topology result. Do not silently repair a polygon and describe it as unchanged.

## Attribution and license

Flanders Marine Institute (2023). *Maritime Boundaries Geodatabase: Maritime Boundaries and Exclusive Economic Zones (200NM), version 12*. https://doi.org/10.14284/632. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Selection of the Vietnam feature and associated boundary lines is the only transformation. Preserve this attribution and a license/source link when displaying the layer. VLIZ requests links to its current products rather than presenting mirrors as authoritative. The [source terms](https://www.marineregions.org/disclaimer.php) state its scientific, educational, and research purpose, disavow legal/navigational use, and state that CC BY terms prevail in case of conflict. CC BY 4.0 permits redistribution and adaptation, including public websites; this is not a certification that the data is suitable for enforcement or navigation. SonarNet uses it only as a visual research reference, never as a legal geofence.

## Important interpretation

The [methodology](https://www.marineregions.org/eezmethodology.php) includes calculated median lines where no treaty is recorded and includes territorial/internal waters in its EEZ polygons. A closed polygon here therefore does **not** mean all its boundary segments are settled international boundaries.

The [line-type definitions](https://www.marineregions.org/eezlinetype.php) distinguish treaties, median lines, connection lines, and unsettled lines. Preserve these distinctions. Treat the whole reference as dashed if rendering only the polygon; do not label it “official boundary”, “territorial waters”, or an exhaustive sovereignty claim.

The source's `Treaty` category is not itself an EEZ certification: its Vietnam–Indonesia segment cites the 2003 **continental-shelf** agreement. A dashed generic research-reference style for all outer segments is the safest minimal presentation; popups may expose the unaltered line classification and source.

Marine Regions holds the South China Sea overlapping-claim polygon separately as [MRGID 49003](https://www.marineregions.org/gazetteer.php?p=details&id=49003); it is not added to Vietnam's polygon here. The source warns that its three sovereign fields cannot enumerate all claimants for that feature. Absence from MRGID 8484 must not be read as rejecting any claim, and inclusion must not be used to decide legality.

Version 2023 must not be presented as current legal data. For example, the [UN Viet Nam state file](https://www.un.org/Depts/los/LEGISLATIONANDTREATIES/STATEFILES/VNM.htm) records a later March 2025 deposit concerning Gulf of Bac Bo baselines and territorial-sea limits. Legal delineation for operational use requires the current competent-authority dataset and domain review.

Suggested compact UI label: **“Tham khảo biển Việt Nam · VLIZ v12”**. Suggested help: “Lớp tham khảo nghiên cứu, không phải ranh giới pháp lý. Các khu vực có yêu sách chồng lấn và đường chưa phân định cần nguồn chuyên ngành.” Keep the actual processed-imagery footprint separately labelled **“Phạm vi đã phân tích”**.
