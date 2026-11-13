# Deprecated scripts (quarantined)

Two scripts used to live here and were removed because they produced artifacts that did
not come from the pipeline:

- `sync_analysis_manifests.py` — rewrote `manifest.json` by hand (fake timings, fake
  perplexity, fake year span).
- `generate_charts_and_snapshots.py` — drew synthetic charts and "screenshots" from
  hard-coded series instead of the Parquet outputs.

The official outputs are now produced only by:

- `src/batch_pipeline.py` (clean data, analysis tables, manifest)
- `src/visualization.py` (all 12 charts + `output/charts/manifest.json`)
- `scripts/build_arxiv_report.py` (report DOCX, template layout) together with
  `scripts/update_report_fields.py` (Word refresh + page numbers + PDF)
- `scripts/build_presentation_slides.py` (slides, reads only verified outputs)

`build_data_mining_style_report.py` was moved here because it wrote the same
`output/reports/BAO_CAO_BAI_TAP_LON_BIGDATA.docx` with the old hand-laid-out
format. Keeping it next to the official builder made it too easy to overwrite a
finished report by mistake; use `build_arxiv_report.py` instead.

Do not reintroduce hand-written numbers into `output/analysis_results/` or
`output/charts/`. Every value in the report and slides must be traceable to a file
produced by the commands above.
