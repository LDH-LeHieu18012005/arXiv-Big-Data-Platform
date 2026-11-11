# Phân tích metadata arXiv bằng Spark, Kafka, HDFS và Hive

Bài tập lớn môn Xử lý Dữ liệu lớn. Hệ thống gồm hai luồng dùng chung tầng lưu trữ HDFS:

- **Batch:** Parquet → Spark (làm sạch, phân tích, LDA) → HDFS → Hive external table → Dashboard/báo cáo.
- **Streaming:** Producer đọc bài báo thật → Kafka → Spark Structured Streaming → HDFS (có checkpoint).

Mọi số liệu hiển thị trên dashboard, báo cáo và slide đều đọc từ tệp kết quả do pipeline sinh ra và
được đối chiếu bằng `clean_run_id`. Không có bảng, biểu đồ hay manifest nào được viết tay.

## Phạm vi dữ liệu

| Hạng mục | Giá trị |
|---|---|
| Nguồn | `VatsaDev/test_arxiv`, revision `adef1f1e891574774660683f0f4548e50f5d551f` |
| Shard | 2 tệp Parquet (`0000.parquet`, `0001.parquet`) |
| Dung lượng | 569.398.929 byte (≈ 543 MB) |
| Bản ghi thô | 704.329 |
| Năm nộp (v1) | 2007 – 2016 |
| Nhóm ngành | 8 (`cs`, `math`, `physics`, `stat`, `q-bio`, `q-fin`, `eess`, `econ`) |

Đây là phạm vi có thật của dữ liệu đã tải; kết quả **không** đại diện cho toàn bộ arXiv.
Chi tiết revision, dung lượng và SHA-256 của từng shard nằm trong `data/source_manifest.json`.

## Quy tắc dữ liệu

- `year` / `submission_year`: năm nộp đầu tiên, lấy từ ngày tạo phiên bản `v1`; nếu thiếu thì suy ra
  từ mã arXiv. Hỗ trợ cả mã cũ (`hep-th/9901001`) và mã mới (`1501.00001`).
- `update_year`: năm cập nhật metadata, không dùng để suy luận xu hướng.
- Bài nộp cuối tháng 12 có thể nhận mã tháng 1 năm sau; chênh lệch giữa năm v1 và năm suy từ mã
  được đếm trong `clean_manifest.json` (`v1_id_year_differences`) thay vì bị loại bỏ.
- Bản ghi thiếu `id`/`title`/`abstract`/`categories` hoặc có năm ngoài khoảng 1991–năm hiện tại
  bị loại và được đếm trong `rejected_rows`.
- Mã bài báo trùng làm pipeline dừng để xử lý nguồn, không tự động chọn một phiên bản.
- `primary_category` là nhãn đầu tiên; `main_group` gộp các archive vật lý vào `physics`.

## Kiến trúc và dịch vụ

`docker-compose.yml` chạy 11 dịch vụ mặc định (12 khi bật thêm worker thứ hai):

| Nhóm | Dịch vụ | Cổng |
|---|---|---|
| HDFS | `namenode`, `datanode` | 9870, 9000, 9864 |
| Kafka | `zookeeper`, `kafka` | 2181, 9092 |
| Hive | `hive-metastore-postgresql`, `hive-metastore`, `hive-server` | 9083, 10000, 10002 |
| Spark | `spark-master`, `spark-worker-1` (2 core, 2 GB), `spark-jupyter` | 8080/7077, 8081, 8888 |
| Ứng dụng | `dashboard` | 8501 |

Các dịch vụ tùy chọn:

- `spark-worker-2` — profile `full`, thêm 2 core/2 GB khi máy đủ tài nguyên.
- `streaming-consumer` — profile `streaming`, chạy Spark Structured Streaming.

```bash
docker compose up -d --build                              # 11 dịch vụ mặc định
docker compose --profile full up -d                       # thêm worker thứ hai
docker compose --profile streaming up -d streaming-consumer
```

## Chạy pipeline

Trong container `spark-jupyter` (hoặc môi trường Python có Spark 3.5.3):

```bash
python src/batch_pipeline.py preprocess      # làm sạch, ghi data/arxiv_clean.parquet + clean_manifest.json
python src/batch_pipeline.py analyze         # 8 bảng phân tích + LDA + manifest.json
python src/visualization.py                  # 12 biểu đồ + forecast_validation.json + charts/manifest.json
python src/batch_pipeline.py sync-hdfs       # ghi Parquet phân vùng theo năm lên HDFS
python src/hive_client.py                    # tạo external table Hive
```

Hoặc chạy gộp bước 1–2: `python src/batch_pipeline.py all`.

Sau khi có dữ liệu stream, làm mới phân vùng Hive:

```python
from hive_client import refresh_all_partitions
refresh_all_partitions()   # MSCK REPAIR cho arxiv_historical và arxiv_stream
```

Dashboard:

```bash
streamlit run src/dashboard_app.py
```

Mở http://localhost:8501.

### Chạy batch không cần Docker

Phần batch và biểu đồ có thể chạy bằng `.venv` với Java 8+ và `winutils` (Windows):

```powershell
$env:HADOOP_HOME = "C:\hadoop"
$env:PATH = "C:\hadoop\bin;$env:PATH"
$env:SPARK_DRIVER_MEMORY = "6g"
$env:PYSPARK_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe)
$env:PYSPARK_DRIVER_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe)
python src/batch_pipeline.py all
python src/visualization.py
```

Phần Hive và streaming cần cụm Docker tương ứng.

## Kết quả sinh ra

```
data/
  source_manifest.json        # repo, revision, shard, dung lượng, SHA-256
  clean_manifest.json         # số dòng thô/sạch/bị loại, năm, mã lần chạy
  arxiv_clean.parquet/        # dữ liệu sạch
output/
  analysis_results/
    manifest.json             # thời gian, cấu hình, model, mã lần chạy
    yearly_growth.parquet
    field_trends.parquet
    top_categories_yearly.parquet
    hot_keyword_trends.parquet
    field_metrics.parquet
    group_terms.parquet
    top_terms.parquet
    top_authors.parquet
    author_trends.parquet
    topics.json
  charts/                     # 12 biểu đồ PNG + manifest.json
  forecast_validation.json    # MAE holdout so với baseline
  forecast_predictions.json   # chỉ chứa từ khóa được chấp nhận
  reports/
    BAO_CAO_BAI_TAP_LON_BIGDATA.docx / .md
    SLIDE_THUYET_TRINH_BIGDATA.pptx
```

Sinh lại báo cáo và slide:

```bash
python scripts/build_data_mining_style_report.py
python scripts/build_presentation_slides.py
```

Hai script này dừng lại nếu mã lần chạy giữa dữ liệu sạch, kết quả phân tích và biểu đồ không khớp.

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Bộ kiểm thử bao gồm quy tắc năm cho mã cũ/mới, loại mã không hợp lệ, gộp nhóm ngành,
schema dữ liệu sạch, sự tồn tại của đủ 12 biểu đồ, tính nhất quán của manifest và
các cột mà dashboard sử dụng.

## Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `SPARK_MASTER` | `local[*]` | Master của Spark |
| `SPARK_DRIVER_MEMORY` | `4g` | Bộ nhớ driver |
| `SPARK_SHUFFLE_PARTITIONS` | `8` | Số partition shuffle |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Broker Kafka |
| `KAFKA_TOPIC` | `arxiv-papers-v2` | Topic sự kiện |
| `HIVE_HOST` / `HIVE_PORT` | `localhost` / `10000` | HiveServer2 |
| `HDFS_NAMENODE` | `hdfs://namenode:9000` | NameNode |

## Hạn chế

- Chỉ phân tích 2 shard đã tải; không suy rộng ra toàn bộ arXiv.
- Tên tác giả chưa được phân giải thực thể.
- Danh sách 16 từ khóa công nghệ là cố định.
- LDA huấn luyện trên mẫu xác định tối đa 200.000 bài để phù hợp tài nguyên máy cá nhân.
- Thời gian chạy phụ thuộc cấu hình máy, không phải benchmark chuẩn.
