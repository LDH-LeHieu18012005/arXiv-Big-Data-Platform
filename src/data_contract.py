"""Data rules used by batch ETL and the Kafka consumer."""
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime

PHYSICS_ARCHIVES = {
    "astro-ph", "cond-mat", "gr-qc", "hep-ex", "hep-lat", "hep-ph",
    "hep-th", "math-ph", "nlin", "nucl-ex", "nucl-th", "physics", "quant-ph",
}
GROUPS = {"cs", "math", "q-bio", "q-fin", "stat", "eess", "econ"}


def year_from_arxiv_id(value):
    """Year of first arXiv submission, including pre-April-2007 IDs."""
    value = str(value or "").removeprefix("arXiv:")
    modern = re.fullmatch(r"(\d{2})(0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?", value)
    legacy = re.fullmatch(r"[a-z-]+(?:\.[A-Z]{2})?/(\d{2})(0[1-9]|1[0-2])\d{3}(?:v\d+)?", value)
    match = modern or legacy
    if not match:
        return None
    yy, month = int(match[1]), int(match[2])
    year = 2000 + yy if modern or yy < 91 else 1900 + yy
    if modern and (year, month) < (2007, 4):
        return None
    if legacy and not (1991 <= year <= 2007 and (year, month) <= (2007, 3)):
        return None
    return year if year <= date.today().year else None


def main_group(category):
    archive = str(category or "").split(".")[0]
    return "physics" if archive in PHYSICS_ARCHIVES else archive if archive in GROUPS else "other"


def year_from_created(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            return None
    return parsed.year if 1991 <= parsed.year <= date.today().year else None


def add_submission_year(df):
    """Prefer the v1 date; use a valid identifier when v1 is absent/unparseable."""
    from pyspark.sql import functions as F
    identifier = F.regexp_replace(F.col("id"), r"^arXiv:", "")
    modern_pattern = r"^(\d{2})(0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?$"
    legacy_pattern = r"^[a-z-]+(?:\.[A-Z]{2})?/(\d{2})(0[1-9]|1[0-2])\d{3}(?:v\d+)?$"
    modern = identifier.rlike(modern_pattern)
    legacy = identifier.rlike(legacy_pattern)
    modern_year = F.regexp_extract(identifier, modern_pattern, 1).cast("int") + 2000
    legacy_yy = F.regexp_extract(identifier, legacy_pattern, 1).cast("int")
    legacy_year = F.when(legacy_yy >= 91, legacy_yy + 1900).otherwise(legacy_yy + 2000)
    modern_month = F.regexp_extract(identifier, modern_pattern, 2).cast("int")
    legacy_month = F.regexp_extract(identifier, legacy_pattern, 2).cast("int")
    id_year = (F.when(modern & ((modern_year > 2007) | ((modern_year == 2007) & (modern_month >= 4))), modern_year)
               .when(legacy & legacy_year.between(1991, 2007) & ((legacy_year < 2007) | (legacy_month <= 3)), legacy_year))
    id_year = F.when(id_year <= date.today().year, id_year)
    df = df.withColumn("id_year", id_year)
    if "versions" in df.columns:
        first = F.element_at(F.filter("versions", lambda v: v["version"] == "v1"), 1)
        df = df.withColumn("submitted_at", first["created"])
    elif "submitted_at" not in df.columns:
        df = df.withColumn("submitted_at", F.lit(None).cast("string"))
    created = F.col("submitted_at")
    rfc_date = F.regexp_replace(created, r"^[A-Za-z]{3},\s*", "")
    timestamp = F.coalesce(F.try_to_timestamp(rfc_date, F.lit("d MMM yyyy HH:mm:ss z")), F.try_to_timestamp(created))
    v1_year = F.year(timestamp)
    v1_year = F.when(v1_year.between(1991, date.today().year), v1_year)
    # New-year announcement IDs can legitimately differ from the December v1 date.
    df = df.withColumn("year", F.when(F.col("id_year").isNotNull(), F.coalesce(v1_year, F.col("id_year"))))
    df = df.withColumn("year_source", F.when(v1_year.isNotNull(), F.lit("v1")).otherwise(F.lit("id")))
    return df.withColumn("submission_year", F.col("year")).withColumn(
        "update_year", F.year("update_date") if "update_date" in df.columns else F.lit(None).cast("int")
    )


def add_categories(df):
    from pyspark.sql import functions as F
    archive = F.element_at(F.split(F.col("primary_category"), r"\."), 1)
    return (df.withColumn("category_list", F.split(F.trim("categories"), r"\s+"))
            .withColumn("primary_category", F.element_at("category_list", 1))
            .withColumn("main_group", F.when(archive.isin(sorted(PHYSICS_ARCHIVES)), "physics")
                        .when(archive.isin(sorted(GROUPS)), archive).otherwise("other")))


def add_tokens(df):
    from pyspark.sql import functions as F
    from pyspark.ml.feature import RegexTokenizer, StopWordsRemover
    clean = F.trim(F.regexp_replace(F.lower("abstract"), r"[^a-z0-9\s-]", " "))
    df = df.withColumn("clean_abstract", clean)
    df = RegexTokenizer(inputCol="clean_abstract", outputCol="_tokens", pattern=r"\s+", minTokenLength=3).transform(df)
    return StopWordsRemover(inputCol="_tokens", outputCol="abstract_tokens").transform(df).drop("_tokens")


def validate_paper(record):
    """Reject malformed messages and incorrect year metadata before publishing."""
    for key in ("id", "title", "abstract", "categories"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Trường {key} phải là chuỗi không rỗng")
    id_year = year_from_arxiv_id(record["id"])
    if id_year is None:
        raise ValueError("ID arXiv không hợp lệ")
    year = year_from_created(record.get("submitted_at")) or id_year
    if record.get("year") is not None and record["year"] != year:
        raise ValueError("Năm nộp bài không khớp với ngày v1/ID arXiv")
    result = dict(record)
    result.update(year=year, primary_category=record["categories"].split()[0])
    result["main_group"] = main_group(result["primary_category"])
    return result
