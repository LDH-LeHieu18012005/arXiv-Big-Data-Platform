-- Versioned locations isolate incompatible old Parquet files.
CREATE DATABASE IF NOT EXISTS arxiv_db;
USE arxiv_db;
DROP VIEW IF EXISTS v_yearly_growth;
DROP VIEW IF EXISTS v_field_distribution;
DROP VIEW IF EXISTS v_top_categories;
-- Only external-table metadata is replaced; data files are retained.
DROP TABLE IF EXISTS arxiv_historical;
CREATE EXTERNAL TABLE arxiv_historical (
 id STRING, title STRING, abstract STRING, authors STRING, categories STRING,
 submission_year INT, update_year INT, primary_category STRING,
 main_group STRING, abstract_tokens ARRAY<STRING>
) PARTITIONED BY (year INT)
STORED AS PARQUET LOCATION 'hdfs://namenode:9000/data/arxiv_clean_v2';
DROP TABLE IF EXISTS arxiv_stream;
-- Column order below matches the Parquet files written by spark_streaming_consumer.py.
CREATE EXTERNAL TABLE arxiv_stream (
 id STRING, title STRING, authors STRING, categories STRING, abstract STRING,
 submitted_at STRING, `timestamp` DOUBLE, year INT, primary_category STRING,
 main_group STRING, clean_abstract STRING, abstract_tokens ARRAY<STRING>,
 processed_time TIMESTAMP
) PARTITIONED BY (main_group_clean STRING)
STORED AS PARQUET LOCATION 'hdfs://namenode:9000/data/arxiv_stream_v2';
DROP TABLE IF EXISTS arxiv_stream_rejects;
-- Quarantine sink written by spark_streaming_consumer.py: same columns as arxiv_stream
-- (year kept as supplied), plus the rejection reason.
CREATE EXTERNAL TABLE arxiv_stream_rejects (
 id STRING, title STRING, authors STRING, categories STRING, abstract STRING,
 submitted_at STRING, supplied_year INT, `timestamp` DOUBLE, year INT,
 primary_category STRING, main_group STRING, clean_abstract STRING,
 abstract_tokens ARRAY<STRING>, reject_reason STRING, processed_time TIMESTAMP,
 main_group_clean STRING
) STORED AS PARQUET LOCATION 'hdfs://namenode:9000/data/arxiv_stream_rejects_v2';
DROP TABLE IF EXISTS hot_keyword_trends;
CREATE EXTERNAL TABLE hot_keyword_trends (
 year INT, word STRING, frequency BIGINT, document_count BIGINT,
 year_total BIGINT, papers_per_1000 DOUBLE
) STORED AS PARQUET LOCATION 'hdfs://namenode:9000/data/hot_keyword_trends_v2';
CREATE VIEW v_yearly_growth AS
 SELECT year, COUNT(*) AS total_papers FROM arxiv_historical GROUP BY year;
CREATE VIEW v_field_distribution AS
 SELECT main_group, COUNT(*) AS total_papers FROM arxiv_historical GROUP BY main_group;
CREATE VIEW v_top_categories AS
 SELECT primary_category, COUNT(*) AS total_papers FROM arxiv_historical GROUP BY primary_category;
