---
inclusion: auto
name: data-dictionary
description: Boston 311 dataset fields, case-type families, closure-reason patterns. Use when writing ingest, detection, or any code that reads 311 data.
---
# Boston 311 data dictionary

**Status: EXPECTED fields — must be verified.** The Data Steward agent verifies every field against the real files (via the DuckDB MCP server) and updates this document, including any differences in records from Boston's newer 311 system (Creatio migration, 2026).

## Source
Analyze Boston dataset "311 Service Requests" (yearly CSV resources, updated daily). License: Open Data Commons PDDL. Use the dataset's **CRM Value Codex** PDF to interpret codes.

## The October 2025 system change
The 311 system changed in October 2025 and **field names differ** (e.g., `open_dt` → `open_date`). Expect three resource groups: yearly legacy files (through 2024), a Jan–Oct 2025 legacy file, and a new-system file (Oct 2025 onward). The ingest layer maps both to the normalized schema and records `system`.

## Source channel (`source`)
Known legacy values: Constituent Call, Citizens Connect App, City Worker App, Self Service, Employee Generated, Twitter, Maximo Integration. City-originated values (Employee Generated, City Worker App, Maximo Integration) matter for planned follow-ups (see zombie-definition.md).

## Related datasets (PDDL, updated nightly)
- Boston Street Segments (SAM system): segment matching.
- Live Street Address Management (SAM) Addresses: "Check my street" search (build a compact client-side index).

## Expected fields (legacy format; verify)
`case_enquiry_id, open_dt, target_dt, closed_dt, ontime, case_status, closure_reason, case_title, subject, reason, type, queue, department, submitted_photo, closed_photo, location, fire_district, pwd_district, city_council_district, police_district, neighborhood, neighborhood_services_district, ward, precinct, location_street_name, location_zipcode, latitude, longitude, source`

## Normalized schema (what the pipeline produces)
`id, open_time, target_time, close_time, on_time (bool|null), status, closure_text, type_raw, type_family, queue, department, neighborhood, district, lat, lon, street, source, system ('legacy'|'new')`

## Type families (fill in after inspecting real `type` values)
Group near-identical types so re-reports match, e.g. potholes, sidewalk repair, streetlight out, missed trash, graffiti, traffic signal, abandoned vehicle. Keep a mapping table in `pipeline/undead311/ingest/type_families.csv`.

## Closure text
Messy, partly templated. Deduplicate templates before labeling. Known pattern to detect: bulk backlog closures (identical text on many cases on the same day).

## Data quality rules
- Drop or flag coordinates outside Boston bounds. Detect placeholder coordinates automatically (points shared by an unusually high number of unrelated cases; known example: City Hall 42.3594, -71.0587).
- Times are local (America/New_York); store UTC + local.
- Scrub personal info (names, phone numbers, emails) from any free text before export.
