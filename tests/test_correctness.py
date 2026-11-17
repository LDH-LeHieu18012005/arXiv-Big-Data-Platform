import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data_contract import year_from_arxiv_id, year_from_created, main_group, validate_paper


class DataRules(unittest.TestCase):
    def test_submission_year_not_update_year(self):
        self.assertEqual(year_from_arxiv_id("0704.0005"), 2007)

    def test_legacy_id_century_and_versions(self):
        for value, expected in [("hep-th/9108001", 1991), ("math.GT/9901001v2", 1999),
                                ("astro-ph/0001001", 2000), ("cs/0703001", 2007),
                                ("arXiv:1501.00001v3", 2015)]:
            with self.subTest(value=value):
                self.assertEqual(year_from_arxiv_id(value), expected)

    def test_invalid_identifiers_rejected(self):
        for value in [None, "", "Author A", "2413.00001", "2400.00001", "0703.0001",
                      "math/0704001", "math/9001001", "9912.00001", "2401.1"]:
            with self.subTest(value=value):
                self.assertIsNone(year_from_arxiv_id(value))

    def test_dates(self):
        self.assertEqual(year_from_created("Mon, 2 Apr 2007 19:18:42 GMT"), 2007)
        self.assertEqual(year_from_created("2024-01-02T00:00:00Z"), 2024)
        for value in [None, "", "not a date 2024", "2024-13-99"]:
            self.assertIsNone(year_from_created(value))

    def test_physics_archives_map_to_one_group(self):
        for value in ["hep-ph", "astro-ph.CO", "cond-mat.mtrl-sci", "quant-ph", "gr-qc"]:
            self.assertEqual(main_group(value), "physics")
        self.assertEqual(main_group("cs.AI"), "cs")
        self.assertEqual(main_group("q-bio.NC"), "q-bio")
        self.assertEqual(main_group(None), "other")

    def test_payload_year_mismatch_is_not_silently_accepted(self):
        record = dict(id="0704.0005", title="Paper", abstract="Text", categories="hep-ph", year=2013)
        with self.assertRaises(ValueError):
            validate_paper(record)
        record["year"] = 2007
        result = validate_paper(record)
        self.assertEqual(result["main_group"], "physics")
        self.assertEqual(result["primary_category"], "hep-ph")

    def test_missing_required_fields_rejected(self):
        with self.assertRaises(ValueError):
            validate_paper(dict(id="2401.00001", title=" ", abstract="x", categories="cs.AI"))

    def test_december_submission_with_january_identifier_is_valid(self):
        record = dict(id="0801.0002", title="Paper", abstract="Text", categories="cs.AI",
                      submitted_at="Fri, 28 Dec 2007 21:06:38 GMT", year=2007)
        self.assertEqual(validate_paper(record)["year"], 2007)


class FailureSemantics(unittest.TestCase):
    def test_hive_failure_does_not_return_cached_results(self):
        import hive_client
        with patch.object(hive_client, "get_hive_connection", side_effect=ConnectionError("Hive down")):
            with self.assertRaises(ConnectionError):
                hive_client.query_hive("SELECT COUNT(*) FROM arxiv_historical")

    def test_kafka_failure_closes_connection_and_raises(self):
        import kafka_producer
        producer = MagicMock()
        producer.send.return_value.get.side_effect = TimeoutError("no ACK")
        with patch.object(kafka_producer, "get_kafka_producer", return_value=producer):
            with self.assertRaises(TimeoutError):
                kafka_producer.send_single_paper(dict(id="2401.00001", title="Paper", abstract="Text", categories="cs.AI"))
        producer.close.assert_called_once()

    def test_missing_or_old_manifest_rejected(self):
        import project_config
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with patch.object(project_config, "RESULTS_DIR", directory):
                with self.assertRaises(RuntimeError):
                    project_config.read_manifest()
                (directory / "manifest.json").write_text('{"schema_version":1}', encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    project_config.read_manifest()


class ForecastRules(unittest.TestCase):
    def test_insufficient_years_produces_no_prediction(self):
        import pandas as pd
        from visualization import forecast_trends
        frame = pd.DataFrame([dict(word="quantum", year=y, year_total=500, papers_per_1000=10)
                              for y in range(2020, 2025)])
        metadata, predictions = forecast_trends(frame, dict(min_year=2020, max_year=2024, clean_run_id="test"))
        self.assertEqual(predictions, [])
        self.assertTrue(all(row["status"] == "insufficient_history" for row in metadata["metrics"]))

    def test_constant_series_is_reported_as_flat(self):
        import pandas as pd
        from visualization import forecast_trends
        frame = pd.DataFrame([dict(word="quantum", year=y, year_total=500, papers_per_1000=0)
                              for y in range(2007, 2021)])
        validation, predictions = forecast_trends(frame, dict(min_year=2007, max_year=2020, clean_run_id="test"))
        self.assertEqual(predictions, [])
        self.assertEqual(validation["metrics"][-1]["status"], "flat_series")

    def test_weak_fit_is_not_published(self):
        import pandas as pd
        from visualization import forecast_trends
        values = [0, 100, 5, 100, 10, 100, 15, 100, 20, 100, 25, 100]
        frame = pd.DataFrame([dict(word="quantum", year=y, year_total=500, papers_per_1000=v)
                              for y, v in zip(range(2007, 2021), values)])
        validation, predictions = forecast_trends(frame, dict(min_year=2007, max_year=2020, clean_run_id="test"))
        self.assertEqual(predictions, [])
        self.assertEqual(validation["metrics"][-1]["status"], "weak_fit")

    def test_linear_series_uses_temporal_holdout_and_bounded_horizon(self):
        import pandas as pd
        from visualization import forecast_trends
        frame = pd.DataFrame([dict(word="quantum", year=y, year_total=500, papers_per_1000=2*(y-2007))
                              for y in range(2007, 2021)])
        validation, predictions = forecast_trends(frame, dict(min_year=2007, max_year=2020, clean_run_id="test"))
        self.assertEqual(validation["metrics"][-1]["test_years"], [2017, 2018, 2019])
        self.assertEqual([p["year"] for p in predictions], [2021, 2022, 2023])
        self.assertLess(validation["metrics"][-1]["mae"], 1e-8)
        self.assertAlmostEqual(validation["metrics"][-1]["r2"], 1.0)


class NotebookChecks(unittest.TestCase):
    def test_notebooks_are_parseable_and_have_no_stale_outputs(self):
        for path in (ROOT / "notebooks").glob("*.ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    with self.subTest(notebook=path.name):
                        ast.parse("".join(cell["source"]))
                        self.assertEqual(cell["outputs"], [])
                        self.assertIsNone(cell["execution_count"])


@unittest.skipUnless(os.getenv("RUN_SPARK_TESTS") == "1", "Set RUN_SPARK_TESTS=1 inside Spark container")
class SparkIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyspark.sql import SparkSession
        os.environ["PYSPARK_PYTHON"] = sys.executable
        cls.spark = (SparkSession.builder.master("local[2]").appName("ArXivCorrectnessTests")
                     .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2")
                     .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_v1_takes_precedence_including_new_year_boundary(self):
        from data_contract import add_submission_year
        frame = self.spark.sql("""
          SELECT '0704.0005' AS id, '2013-10-15' AS update_date,
            array(named_struct('version','v1','created','Mon, 2 Apr 2007 19:18:42 GMT')) AS versions
          UNION ALL SELECT '0801.0002', '2015-01-01',
            array(named_struct('version','v1','created','Fri, 28 Dec 2007 21:06:38 GMT'))
          UNION ALL SELECT 'hep-th/9108001', '2009-01-01',
            cast(array() AS array<struct<version:string,created:string>>)
        """)
        rows = {r.id: r.asDict() for r in add_submission_year(frame).collect()}
        self.assertEqual(rows["0704.0005"]["year"], 2007)
        self.assertEqual(rows["0704.0005"]["update_year"], 2013)
        self.assertEqual(rows["0801.0002"]["year"], 2007)
        self.assertEqual(rows["0801.0002"]["id_year"], 2008)
        self.assertEqual(rows["hep-th/9108001"]["year"], 1991)

    def test_missing_years_do_not_become_adjacent_year_growth(self):
        from batch_pipeline import with_growth
        frame = self.spark.sql("SELECT * FROM VALUES (2020, 10L), (2021, 0L), (2022, 20L) AS t(year,count)")
        rows = with_growth(frame, [], "count").orderBy("year").collect()
        self.assertEqual(rows[1].yoy_growth_rate, -100)
        self.assertIsNone(rows[2].yoy_growth_rate)

    def test_shared_nlp_and_categories(self):
        from data_contract import add_categories, add_tokens
        frame = self.spark.sql("SELECT 'The SELF-SUPERVISED model, and quantum!' AS abstract, 'hep-ph cs.AI' AS categories")
        row = add_tokens(add_categories(frame)).first()
        self.assertEqual(row.main_group, "physics")
        self.assertEqual(row.primary_category, "hep-ph")
        self.assertEqual(row.abstract_tokens, ["self-supervised", "model", "quantum"])

    def test_all_analysis_queries_with_storage_boundary_mocked(self):
        import batch_pipeline
        from pyspark.sql.readwriter import DataFrameReader, DataFrameWriter
        frame = self.spark.sql("""
          SELECT '0704.0001' AS id, 2007 AS year, 'physics' AS main_group,
           'hep-ph' AS primary_category, array('quantum','quantum','models') AS abstract_tokens,
           array(array('Doe','Jane','')) AS authors_parsed,
           28 AS abstract_length, 3 AS token_count, 12 AS title_length
          UNION ALL SELECT '0901.0001', 2009, 'cs', 'cs.AI',
           array('quantum','attention','models'), array(array('Doe','Jane',''),array('Smith','John','')),
           30, 3, 10
        """)
        captured = {}
        def capture(writer, path):
            captured[Path(path).name] = writer._df.collect()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "clean_manifest.json").write_text(json.dumps(dict(schema_version=2,
                clean_run_id="fixture", rows=2, min_year=2007, max_year=2009, seconds=0)), encoding="utf-8")
            with patch.object(batch_pipeline, "DATA_DIR", directory), patch.object(batch_pipeline, "RESULTS_DIR", directory / "results"), \
                 patch.object(DataFrameReader, "parquet", return_value=frame), \
                 patch.object(DataFrameWriter, "parquet", autospec=True, side_effect=capture):
                manifest = batch_pipeline.analyze(self.spark, train_clusters=False)
        self.assertEqual(manifest["rows"], 2)
        self.assertEqual(manifest["groups"], 2)
        yearly = sorted(captured["yearly_growth.parquet"], key=lambda r:r.year)
        self.assertEqual([r["count"] for r in yearly], [1, 0, 1])
        self.assertIsNone(yearly[-1].yoy_growth_rate)
        quantum = next(r for r in captured["hot_keyword_trends.parquet"] if r.year == 2007 and r.word == "quantum")
        self.assertEqual((quantum.frequency, quantum.document_count, quantum.papers_per_1000), (2, 1, 1000.0))
        jane = next(r for r in captured["top_authors.parquet"] if r.author == "Jane Doe")
        self.assertEqual(jane["count"], 2)

    def test_kmeans_training_has_heldout_metrics_and_real_vocabulary(self):
        import batch_pipeline
        from pyspark.sql.readwriter import DataFrameReader, DataFrameWriter
        from pyspark.ml.util import JavaMLWriter
        frame = self.spark.sql("""
          SELECT concat('0901.',lpad(cast(id+1 AS string),4,'0')) AS id, 2009 AS year,
           'cs' AS main_group, 'cs.AI' AS primary_category,
           CASE WHEN id % 2 = 0 THEN array('quantum','physics','models')
                ELSE array('neural','attention','models') END AS abstract_tokens,
           array(array('Doe','Jane','')) AS authors_parsed,
           25 AS abstract_length, 3 AS token_count, 9 AS title_length
          FROM range(30)
        """)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "clean_manifest.json").write_text(json.dumps(dict(schema_version=2,
                clean_run_id="fixture-model", rows=30, min_year=2009, max_year=2009, seconds=0)), encoding="utf-8")
            with patch.object(batch_pipeline, "DATA_DIR", directory), patch.object(batch_pipeline, "RESULTS_DIR", directory / "results"), \
                 patch.object(DataFrameReader, "parquet", return_value=frame), \
                 patch.object(DataFrameWriter, "parquet", autospec=True), patch.object(JavaMLWriter, "save", autospec=True):
                manifest = batch_pipeline.analyze(self.spark, clusters=2, train_clusters=True)
            self.assertEqual(manifest["model"]["status"], "trained")
            self.assertEqual(manifest["model"]["model_type"], "kmeans")
            self.assertGreater(manifest["model"]["test_documents"], 0)
            import math
            self.assertTrue(math.isfinite(manifest["model"]["train_wsse"]))
            self.assertLess(manifest["model"]["train_mean_sq_distance"], 4.0)
            clusters = json.loads((directory / "results/clusters.json").read_text(encoding="utf-8"))
            self.assertEqual(len(clusters), 2)
            self.assertTrue(all(isinstance(word, str) for cluster in clusters for word in cluster["terms"]))
            self.assertAlmostEqual(sum(cluster["share"] for cluster in clusters), 1.0)

    @unittest.skipIf(os.name == "nt", "Spark Parquet writes require native Hadoop on Windows; run in Linux container")
    def test_batch_pipeline_writes_consistent_outputs_from_raw_data(self):
        import batch_pipeline
        import project_config
        from pyspark.sql import functions as F
        raw = self.spark.createDataFrame([
            ("0704.0001", "First", "quantum quantum models", "hep-ph", "2013-10-15"),
            ("0901.0001", "Second", "quantum attention models", "cs.AI", "2024-01-01"),
            ("0901.0002", " ", "invalid empty title", "math.PR", "2024-01-01"),
        ], "id string, title string, abstract string, categories string, update_date string")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            results = Path(tmp) / "output" / "analysis_results"
            data.mkdir()
            raw.write.parquet(str(data / "arxiv_data.parquet"))
            with patch.object(batch_pipeline, "DATA_DIR", data), patch.object(batch_pipeline, "RESULTS_DIR", results), \
                 patch.object(project_config, "DATA_DIR", data), patch.object(project_config, "RESULTS_DIR", results):
                clean = batch_pipeline.preprocess(self.spark)
                manifest = batch_pipeline.analyze(self.spark, train_clusters=False)
                self.assertEqual(clean["rejected_rows"], 1)
                self.assertEqual(manifest["rows"], 2)
                self.assertEqual((manifest["min_year"], manifest["max_year"]), (2007, 2009))
                yearly = self.spark.read.parquet(str(results / "yearly_growth.parquet")).orderBy("year").collect()
                self.assertEqual([r["count"] for r in yearly], [1, 0, 1])
                self.assertIsNone(yearly[-1].yoy_growth_rate)
                keywords = self.spark.read.parquet(str(results / "hot_keyword_trends.parquet"))
                quantum = keywords.filter("word = 'quantum' AND year = 2007").first()
                self.assertEqual(quantum.frequency, 2)
                self.assertEqual(quantum.document_count, 1)
                self.assertEqual(quantum.papers_per_1000, 1000)
                self.assertEqual(project_config.read_manifest()["clean_run_id"], clean["clean_run_id"])


class PublishedArtifacts(unittest.TestCase):
    """Guards the files that the dashboard, report and slides consume."""

    def setUp(self):
        self.clean = ROOT / "data" / "clean_manifest.json"
        self.source = ROOT / "data" / "source_manifest.json"
        self.result = ROOT / "output" / "analysis_results" / "manifest.json"
        self.charts = ROOT / "output" / "charts" / "manifest.json"
        self.forecast = ROOT / "output" / "forecast_validation.json"
        missing = [str(p) for p in (self.clean, self.source, self.result, self.charts, self.forecast)
                   if not p.exists()]
        if missing:
            self.skipTest("Chưa chạy pipeline: " + ", ".join(missing))

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_source_is_at_least_300_mb_and_hashed(self):
        source = self.read(self.source)
        self.assertGreaterEqual(source["total_bytes"], 300 * 1024 * 1024)
        self.assertEqual(len(source["shards"]), 2)
        self.assertGreaterEqual(len(source["shards"][0]["sha256"]), 64)
        self.assertEqual(source["total_bytes"], sum(item["bytes"] for item in source["shards"]))

    def test_manifests_describe_the_same_run(self):
        clean, result = self.read(self.clean), self.read(self.result)
        self.assertEqual(clean["schema_version"], result["schema_version"])
        self.assertEqual(clean["clean_run_id"], result["clean_run_id"])
        self.assertEqual(clean["rows"], result["rows"])
        self.assertEqual((clean["min_year"], clean["max_year"]),
                         (result["min_year"], result["max_year"]))
        self.assertEqual(clean["raw_rows"] - clean["rejected_rows"], clean["rows"])

    def test_yearly_growth_matches_row_count(self):
        import pandas as pd
        result = self.read(self.result)
        yearly = pd.read_parquet(ROOT / "output" / "analysis_results" / "yearly_growth.parquet")
        self.assertIn("count", yearly.columns)
        self.assertIn("yoy_growth_rate", yearly.columns)
        self.assertNotIn("paper_count", yearly.columns)
        self.assertEqual(int(yearly["count"].sum()), result["rows"])
        self.assertEqual(sorted(yearly["year"].tolist()),
                         list(range(result["min_year"], result["max_year"] + 1)))

    def test_field_tables_are_consistent(self):
        import pandas as pd
        result = self.read(self.result)
        base = ROOT / "output" / "analysis_results"
        fields = pd.read_parquet(base / "field_trends.parquet")
        metrics = pd.read_parquet(base / "field_metrics.parquet")
        terms = pd.read_parquet(base / "group_terms.parquet")
        self.assertEqual(metrics["main_group"].nunique(), result["groups"])
        self.assertEqual(int(metrics["papers"].sum()), result["rows"])
        shares = fields.groupby("year")["percentage_share"].sum()
        for year, value in shares.items():
            self.assertAlmostEqual(float(value), 100.0, places=4, msg=f"year {year}")
        self.assertLessEqual(int(terms["rank"].max()), 50)

    def test_all_twelve_charts_exist(self):
        manifest = self.read(self.charts)
        self.assertEqual(len(manifest["charts"]), 12)
        for name in manifest["charts"]:
            self.assertTrue((ROOT / "output" / "charts" / name).exists(), name)
        self.assertNotIn("10_trend_forecast_2030.png", manifest["charts"])

    def test_forecast_is_bounded_and_published_only_with_strong_fit(self):
        forecast = self.read(self.forecast)
        result = self.read(self.result)
        published = {item["word"] for item in forecast["metrics"] if item["status"] == "ok"}
        self.assertTrue(all(item.get("r2") is None or item["r2"] >= 0.5
                            for item in forecast["metrics"] if item["status"] == "ok"))
        predictions_path = ROOT / "output" / "forecast_predictions.json"
        if predictions_path.exists():
            predictions = self.read(predictions_path)["predictions"]
            self.assertEqual({item["word"] for item in predictions}, published)
            self.assertTrue(all(item["year"] <= result["max_year"] + 3 for item in predictions))
            self.assertTrue(all(item["year"] > result["max_year"] for item in predictions))

    def test_dashboard_matches_published_schema(self):
        source = (ROOT / "src" / "dashboard_app.py").read_text(encoding="utf-8")
        for required in ('yearly["count"]', 'yoy_growth_rate', 'field_trends.parquet',
                         'main_group', "refresh_all_partitions"):
            self.assertIn(required, source)
        for stale in ("trend_forecast_2030", "19 năm", "7.82", "paper_count\"]"):
            self.assertNotIn(stale, source)

    def test_report_and_slides_exist(self):
        report = ROOT / "output" / "reports" / "BAO_CAO_BAI_TAP_LON_BIGDATA.docx"
        slides = ROOT / "output" / "reports" / "SLIDE_THUYET_TRINH_BIGDATA.pptx"
        for path, minimum in ((report, 20_000), (slides, 20_000)):
            self.assertTrue(path.exists(), path)
            self.assertGreater(path.stat().st_size, minimum, path)


if __name__ == "__main__":
    unittest.main()
