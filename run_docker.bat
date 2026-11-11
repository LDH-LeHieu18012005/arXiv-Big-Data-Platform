@echo off
chcp 65001 > nul
echo ======================================================================
echo    KHOI DONG CUM PHAN TAN BIG DATA TOAN DIEN (12 CONTAINERS)
echo    Kafka -> Spark Streaming -> HDFS -> Hive -> Streamlit Dashboard
echo ======================================================================
echo.

echo [1/2] Kiem tra Docker Desktop...
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Docker chua duoc bat! Vui long mo Docker Desktop truoc.
    pause
    exit /b 1
)

echo [2/2] Khoi dong Cum phan tan voi Docker Compose...
docker compose up -d --build

if %errorlevel% neq 0 (
    echo.
    echo [LOI] Khong the khoi dong cum container! Vui long kiem tra Docker daemon.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo           DA GUI LENH KHOI DONG - CAN KIEM TRA TRANG THAI!
echo ======================================================================
echo.
echo  [1] Giao dien Demo Dashboard (Streamlit):
echo      👉 http://localhost:8501  (Day Kafka, xem HDFS, Hive SQL & Charts)
echo.
echo  [2] Giao dien Lap trinh JupyterLab:
echo      👉 http://localhost:8888  (Mat khau / Token: bigdata2026)
echo.
echo  [3] Giao dien Quan tri Ha tang Big Data:
echo      * Spark Master Cluster UI:  http://localhost:8080 (Theo doi Cores & RAM)
echo      * HDFS NameNode Web UI:     http://localhost:9870 (Quan ly file tren HDFS)
echo      * HiveServer2 Web UI:       http://localhost:10002
echo      * Spark Driver UI:          http://localhost:4040
echo.
echo  Danh sach 12 container trong he thong:
echo    - namenode, datanode            (Hadoop HDFS Storage)
echo    - zookeeper, kafka              (Kafka Message Broker)
echo    - hive-metastore-postgresql     (Hive Metastore DB)
echo    - hive-metastore, hive-server   (Apache Hive SQL Data Warehouse)
echo    - spark-master, spark-worker-1,2(Apache Spark Cluster)
echo    - spark-jupyter                 (Client Driver & 8 Notebooks)
echo    - dashboard                     (Streamlit Web Demo)
echo ======================================================================
pause
