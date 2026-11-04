# Sources for control, occupation and ceasefire layers

Last reviewed: 4 November 2026.

## How to load data into the map

The map has three layers that accept files. Choose **Contested control → Load control areas…** or **Load occupied areas…**:

| Layer | Style | Use for |
|---|---|---|
| Non-state actor control | Red outline | Rebel, militia and breakaway authorities |
| Occupied territory | Maroon fill | Ground held by another state's forces |
| DMZs, buffer zones & ceasefire lines | Cyan dashed | Demilitarised zones and armistice or control lines (built in) |

- **Formats:** any polygon GeoJSON works. These property names are read if present: `name`, `actor` or `occupier`, `kind`, `precision`, `as_of`, `note`, `sources` / `source_url`. The occupied loader also accepts Military Summary's raw API format.
- **Converting files:** shapefile, KML or KMZ → GeoJSON with https://mapshaper.org, QGIS, or `ogr2ogr -f GeoJSON out.geojson in.shp`.
- **Auto-loading:** a file saved as `data/occupied.js` (`window.OCCUPIED_AREAS = {…FeatureCollection…};`) loads automatically when the map opens.

## Licensing (check before loading anything)

| Source | Can it go on the map? |
|---|---|
| **ISW / CTP** (understandingwar.org, criticalthreats.org) | **Not without permission.** ISW's ArcGIS items state the geodata "is the exclusive intellectual property of ISW" and "may not be used without the written consent of ISW". The data is technically reachable, but you would need to ask ISW for written permission first. |
| **Military Summary** (militarysummary.com/map) | **Unclear.** No licence or terms are published, and the API blocks other websites. A private snapshot is possible, but nothing grants permission. The layers are drawn by one independent channel. |
| **DeepStateMap** (deepstatemap.live) | **Check their terms first.** No published open-data licence was found. |
| **Natural Earth** | **Yes.** Public domain. Used for the built-in breakaway, disputed, DMZ and long-standing occupation layers. |
| **ACAPS / OCHA / HDX** | **Usually yes,** often CC BY or CC BY-IGO with attribution. Check each dataset's page. |
| **ACLED, UCDP** | **Yes for non-commercial use,** with attribution and, for ACLED, a free account. |
| **OpenStreetMap** | **Yes,** under ODbL (attribution and share-alike). |
| **Wikipedia / Wikimedia Commons maps** | **Yes,** under CC BY-SA. |
| **PolGeoNow, Sudans Post, Hiraal** | **No.** Copyrighted maps (PolGeoNow is subscription). Use them to check outlines, not to copy them. |

## Built in

| Layer | Area | Source | Notes |
|---|---|---|---|
| Non-state | Abkhazia, South Ossetia, Transnistria, N. Cyprus, Somaliland | Natural Earth | Boundary-level |
| Non-state | Houthi Yemen; RSF Darfur; M23 eastern DRC | geoBoundaries units, merged | Approximate, mid-2026 |
| Occupied | Crimea; Donetsk and Luhansk pre-2022 lines | Natural Earth | **Pre-2022 extent only.** The current front needs a permitted source |
| Occupied | Golan Heights; West Bank; East Jerusalem | Natural Earth | UN view: occupied since 1967 |
| DMZ / lines | Korean DMZ and Military Demarcation Line; Cyprus UN buffer zone and Green Line; UNDOF zone and 1974 Golan lines; Kashmir LoC; Siachen front; China–India disputed sectors; Israel–Lebanon line; Western Sahara berm | Natural Earth | Static treaty and ceasefire lines |
| Disputed | About 75 claims (Kashmir, W. Sahara, Taiwan, South China Sea…) | Natural Earth | Orange dashed, off by default |

## Conflict by conflict

### Russia–Ukraine
- **ISW interactive map.** Updated daily (last: 3 Nov 2026); needs written permission. https://isw.pub/InteractiveUkraineWarMap
- **DeepStateMap.** Daily updates from a Ukrainian volunteer project. Licence unclear. https://deepstatemap.live
- **Military Summary.** Independent channel; no licence. https://militarysummary.com/map
- **Wikipedia: Module:Russo-Ukrainian War detailed map.** Settlement-level points, CC BY-SA.

### Israel–Palestine, Lebanon, southern Syria
- **Gaza "Yellow Line" (since the Oct 2025 ceasefire) and "Orange Line" (since spring 2026).**
  - No open GIS file is published. The IDF distributes maps to aid groups, and OCHA oPt republishes summaries.
  - Israeli-held share reported at 53% at the ceasefire, about two-thirds by May 2026.
  - Sources: OCHA oPt (https://www.ochaopt.org), Wikipedia "Yellow Line (Gaza)".
- **West Bank Areas A/B/C, settlements and the barrier.**
  - Peace Now GIS layers (free download): https://peacenow.org.il/en?p=44841
  - OCHA oPt maps: https://www.ochaopt.org/page/interactive-map
  - Palestinian Central Bureau of Statistics geodata.
- **South Lebanon and southern Syria.**
  - ISW tracks Israeli positions in Lebanon (updated 3 Nov 2026) and in Syria (needs permission).
  - ACLED event data shows Israeli incursions.

### Syria
- **Carter Center Syria Conflict Mapping.** Locality-level control since 2014: https://www.cartercenter.org
- **ACLED's "Mapping Territorial Control in Syria"** (quarterly reports).
- **PolGeoNow** (subscription; Aug 2026 map shows the SDF formally dissolved, Israeli-held southwest, Druze-held Suwayda).
- **ISW/CTP "Assessed Control of Terrain in Syria"** (needs permission).

### Yemen
- **ACAPS "Yemen: Areas of control" (HDX).** District-level (Admin 2) GIS layer: https://data.humdata.org/dataset/8a7cb6f6-bcf9-4cdc-8e2a-4f2d1e378cba
- **Crisis Group Yemen conflict map:** https://yemenconflict.crisisgroup.org/
- **PolGeoNow Yemen** (subscription; Feb 2026 map covers the collapse of STC control).

### Sudan
- **Sudans Post Geospatial.** Monthly territorial control maps (images, 2026): https://www.sudanspost.com
- **Africa Center for Strategic Studies "Mapping the Armed Actors in the Sudan Conflict"** (Jul 2026).
- **Sudan War Monitor:** https://sudanwarmonitor.com
- **CTP Africa File / Sudan maps** (needs permission). **ACLED** events.

### Myanmar
- **ISP-Myanmar.** Resistance-controlled towns and territory (data to May–July 2026): https://ispmyanmar.com
- **BNI Myanmar Peace Monitor.** Township-level control: https://mmpeacemonitor.org
- **SAC-M "Effective Control in Myanmar"** (township-level, 2024): https://specialadvisorycouncil.org

### Sahel (Mali, Burkina Faso, Niger)
- **CTP "Salafi-Jihadi Areas of Operation in the Sahel / West Africa"** (support zones; needs permission): https://www.criticalthreats.org/analysis/salafi-jihadi-areas-of-operation-in-the-sahel
- **ACLED** (JNIM, IS Sahel events). Reports put JNIM's effective control at about 40–60% of Burkina Faso.

### Somalia
- **PolGeoNow** (subscription; village-level, Apr 2026).
- **Hiraal Institute control and influence map:** https://hiraalinstitute.org/somalia-map-control-and-influence/
- **EUAA COI reports** (collect maps with sourcing): https://euaa.europa.eu

### DR Congo (M23/AFC)
- **CTP Congo War Security Review.** Maps several times a week; shapefiles by email request: https://www.criticalthreats.org/briefs/congo-war-security-review
- **IPIS:** https://ipisresearch.be/home/maps-data/maps-of-drc/mapping-the-m23s-territorial-influence-in-eastern-drc/

### Ethiopia (Amhara, Fano)
- **No reliable control polygons.** Control shifts often. Use ACLED events. Wikipedia "War in Amhara" has a presence map (CC BY-SA). The main Fano factions merged into the AFNM in Jan 2026.

### Mozambique (Cabo Delgado)
- **Cabo Ligado / ACLED.** **PolGeoNow** close-up maps (subscription).

### Nagorno-Karabakh / Armenia–Azerbaijan
- **No active control line.** Azerbaijan retook all of Nagorno-Karabakh in Sept 2023, the Artsakh republic dissolved, and a peace agreement was initialled in Aug 2025.
- **Still drawable:** Natural Earth keeps the 2020 ceasefire and 1991 oblast reference lines. Small Azerbaijani-held positions inside Armenia since 2021–22 have no open dataset.

### Kashmir, Korea, Cyprus, Golan (frozen lines)
- **Built in** from Natural Earth: Line of Control, Siachen front, Korean DMZ and MDL, Cyprus buffer zone and Green Line, UNDOF zone. Also available in OSM as `boundary=disputed` / ceasefire ways.

### Haiti, Libya, Western Sahara, others
- **Haiti:** gang control of Port-au-Prince, from UN BINUH / OCHA and ACLED reports (no open polygons).
- **Libya:** east–west split (LNA vs GNU), from ACLED and Wikipedia maps.
- **Western Sahara:** the Moroccan berm is built in. The area east of it is Polisario-held.

## General datasets
- **ACLED.** Global event data with "non-state actor overtakes territory" events: https://acleddata.com
- **UCDP GED.** Georeferenced events: https://ucdp.uu.se/downloads/
- **UCDP / PRIO conflict-site polygons** (historical activity zones).
- **Liveuamap.** Near-real-time events; its control areas are algorithmic: https://liveuamap.com
