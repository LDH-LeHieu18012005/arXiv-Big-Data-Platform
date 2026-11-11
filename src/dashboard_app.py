"""
================================================================================
🌌 arXiv Big Data Studio — Executive Analytics & Distributed Pipeline Dashboard
Kiến trúc phân tán: Kafka → Spark Streaming → HDFS Lakehouse → Hive DW → Dashboard
================================================================================
"""
import json
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_contract import year_from_arxiv_id
from project_config import DATA_DIR, OUTPUT_DIR, RESULTS_DIR, read_manifest
from kafka_producer import get_kafka_producer, send_single_paper, sample_papers_from_local
from hdfs_helper import check_hdfs_status, list_hdfs_dir
from hive_client import query_hive, test_hive_connection, refresh_all_partitions

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG & THEME
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="arXiv Big Data Platform",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End CSS Styling
CUSTOM_CSS = """
<style>
/* Modern Fonts & Base Styles */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header Gradient Banner */
.hero-banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 24px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
}

.hero-title {
    font-size: 2.1rem;
    font-weight: 800;
    background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 6px;
}

.hero-subtitle {
    color: #94a3b8;
    font-size: 1.0rem;
    font-weight: 400;
    margin-bottom: 16px;
}

.badge-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
}

.tech-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.2);
    color: #e2e8f0;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    backdrop-filter: blur(4px);
}

.tech-badge.spark { border-color: rgba(249, 115, 22, 0.4); color: #fb923c; }
.tech-badge.kafka { border-color: rgba(6, 182, 212, 0.4); color: #22d3ee; }
.tech-badge.hdfs { border-color: rgba(234, 179, 8, 0.4); color: #facc15; }
.tech-badge.hive { border-color: rgba(168, 85, 247, 0.4); color: #c084fc; }
.tech-badge.streamlit { border-color: rgba(244, 63, 94, 0.4); color: #fb7185; }

/* Metric KPI Cards */
.kpi-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.kpi-card {
    background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 14px;
    padding: 18px 20px;
    transition: all 0.25s ease;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
}

.kpi-card:hover {
    transform: translateY(-3px);
    border-color: rgba(99, 102, 241, 0.4);
    box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.15);
}

.kpi-label {
    font-size: 0.82rem;
    font-weight: 500;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}

.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #f8fafc;
    line-height: 1.2;
}

.kpi-desc {
    font-size: 0.78rem;
    color: #38bdf8;
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 4px;
}

/* Status Indicators */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 30px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 8px;
}

.status-online {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.35);
    color: #34d399;
}

.status-offline {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #f87171;
}

.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}

.dot.green { background-color: #10b981; box-shadow: 0 0 8px #10b981; }
.dot.red { background-color: #ef4444; box-shadow: 0 0 8px #ef4444; }

/* Section Header */
.section-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-top: 8px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 2px solid rgba(99, 102, 241, 0.2);
    padding-bottom: 8px;
}

/* Gallery Cards */
.gallery-card {
    background: #1e293b;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 16px;
    transition: all 0.2s ease;
}

.gallery-card:hover {
    border-color: rgba(56, 189, 248, 0.5);
    box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.3);
}

.gallery-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #f8fafc;
    margin-bottom: 6px;
}

.gallery-caption {
    font-size: 0.8rem;
    color: #94a3b8;
    line-height: 1.4;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background: #0b0f19;
    border-right: 1px solid rgba(148, 163, 184, 0.1);
}

/* Tab Active Styles */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.stTabs [data-baseweb="tab"] {
    padding: 10px 20px;
    font-weight: 600;
    border-radius: 8px 8px 0 0;
    color: #94a3b8;
}

.stTabs [aria-selected="true"] {
    color: #38bdf8 !important;
    background: rgba(56, 189, 248, 0.08) !important;
    border-bottom: 3px solid #38bdf8 !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. APP STATE & CONFIG
# -----------------------------------------------------------------------------
if "event_history" not in st.session_state:
    st.session_state.event_history = []

kafka_server = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
topic = os.getenv("KAFKA_TOPIC", "arxiv-papers-v2")


def tcp_status(host, port, timeout=2.0):
    """Return True only when a TCP handshake succeeds."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


kafka_host, _, kafka_port = kafka_server.partition(":")
kafka_ok = tcp_status(kafka_host or "localhost", kafka_port or 9092)
spark_ok = tcp_status(os.getenv("SPARK_MASTER_HOST", "spark-master"), 7077)

# -----------------------------------------------------------------------------
# 3. SIDEBAR: CLUSTER HEALTH & QUICK ACCESS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🌌 arXiv Big Data Studio")
    st.caption("Cụm phân tán · 11 dịch vụ mặc định")

    st.markdown("---")
    st.markdown("#### ⚡ Giám sát Cụm Dịch vụ")

    kafka_class = "status-online" if kafka_ok else "status-offline"
    kafka_dot = "green" if kafka_ok else "red"
    kafka_text = "ONLINE" if kafka_ok else "OFFLINE"
    st.markdown(f"""
    <div style="background: rgba(30,41,59,0.7); padding: 10px 14px; border-radius: 10px; margin-bottom: 8px; border: 1px solid rgba(148,163,184,0.15);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; font-size: 0.85rem; color: #e2e8f0;">Apache Kafka</span>
            <span class="status-pill {kafka_class}" style="padding: 2px 8px; font-size: 0.72rem;"><span class="dot {kafka_dot}"></span> {kafka_text}</span>
        </div>
        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 4px;">Broker: <code>{kafka_server}</code></div>
    </div>
    """, unsafe_allow_html=True)

    # Check HDFS status
    hdfs_info = check_hdfs_status()
    hdfs_is_online = (hdfs_info.get("status") == "ONLINE")
    hdfs_class = "status-online" if hdfs_is_online else "status-offline"
    hdfs_dot = "green" if hdfs_is_online else "red"
    hdfs_status_text = "ONLINE" if hdfs_is_online else "OFFLINE"
    st.markdown(f"""
    <div style="background: rgba(30,41,59,0.7); padding: 10px 14px; border-radius: 10px; margin-bottom: 8px; border: 1px solid rgba(148,163,184,0.15);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; font-size: 0.85rem; color: #e2e8f0;">Hadoop HDFS</span>
            <span class="status-pill {hdfs_class}" style="padding: 2px 8px; font-size: 0.72rem;"><span class="dot {hdfs_dot}"></span> {hdfs_status_text}</span>
        </div>
        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 4px;">NameNode: <code>hdfs://namenode:9000</code></div>
    </div>
    """, unsafe_allow_html=True)

    # Check Hive status
    hive_ok, hive_msg = test_hive_connection()
    hive_class = "status-online" if hive_ok else "status-offline"
    hive_dot = "green" if hive_ok else "red"
    hive_status_text = "ONLINE" if hive_ok else "DISCONNECTED"
    st.markdown(f"""
    <div style="background: rgba(30,41,59,0.7); padding: 10px 14px; border-radius: 10px; margin-bottom: 8px; border: 1px solid rgba(148,163,184,0.15);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; font-size: 0.85rem; color: #e2e8f0;">Apache Hive</span>
            <span class="status-pill {hive_class}" style="padding: 2px 8px; font-size: 0.72rem;"><span class="dot {hive_dot}"></span> {hive_status_text}</span>
        </div>
        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 4px;">Thrift: <code>Port 10000 (arxiv_db)</code></div>
    </div>
    """, unsafe_allow_html=True)

    # Check Spark status
    spark_class = "status-online" if spark_ok else "status-offline"
    spark_dot = "green" if spark_ok else "red"
    spark_text = "ONLINE" if spark_ok else "OFFLINE"
    st.markdown(f"""
    <div style="background: rgba(30,41,59,0.7); padding: 10px 14px; border-radius: 10px; margin-bottom: 16px; border: 1px solid rgba(148,163,184,0.15);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; font-size: 0.85rem; color: #e2e8f0;">Apache Spark</span>
            <span class="status-pill {spark_class}" style="padding: 2px 8px; font-size: 0.72rem;"><span class="dot {spark_dot}"></span> {spark_text}</span>
        </div>
        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 4px;">Master: <code>spark-master:7077</code> · 2 workers / 4 cores</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 🔗 Cổng dịch vụ Web UI")
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.link_button("⚡ Spark UI", "http://localhost:8080", use_container_width=True)
        st.link_button("🐘 HDFS UI", "http://localhost:9870", use_container_width=True)
    with col_l2:
        st.link_button("📓 JupyterLab", "http://localhost:8888", use_container_width=True)
        st.link_button("🏛️ Hive Web", "http://localhost:10002", use_container_width=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-size: 0.75rem; color: #64748b; line-height: 1.5;">
        <b>Tài nguyên cụm:</b><br/>
        • 12 Docker Containers<br/>
        • Spark: 1 Master, 2 Workers (4 Cores, 4GB RAM)<br/>
        • Hadoop HDFS (1 NameNode, 1 DataNode)<br/>
        • Hive Metastore + PostgreSQL Backend<br/>
        • Kafka 7.6.0 + Zookeeper
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. TOP HERO BANNER
# -----------------------------------------------------------------------------
st.markdown("""
<div class="hero-banner">
    <div class="hero-title">🌌 Nền Tảng Phân Tích Dữ Liệu Lớn arXiv</div>
    <div class="hero-subtitle">
        Khám phá xu hướng nghiên cứu khoa học toàn cầu qua kiến trúc Big Data phân tán tích hợp: Batch Analytics, Real-time Streaming, Data Lakehouse & SQL Warehouse.
    </div>
    <div class="badge-row">
        <span class="tech-badge spark">⚡ Apache Spark 3.5.3</span>
        <span class="tech-badge kafka">📨 Apache Kafka 7.6.0</span>
        <span class="tech-badge hdfs">🐘 Hadoop HDFS 3.2.1</span>
        <span class="tech-badge hive">🏛️ Apache Hive 2.3.2</span>
        <span class="tech-badge streamlit">📊 Streamlit 1.40.0</span>
        <span class="tech-badge">🐳 12 Containers</span>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. MAIN NAVIGATION TABS
# -----------------------------------------------------------------------------
tab_analytics, tab_kafka, tab_streaming, tab_hive, tab_architecture = st.tabs([
    "📊 Phân tích & Trực quan hóa",
    "🚀 Thu nhận Stream (Kafka)",
    "🌊 Xử lý Luồng & HDFS Lakehouse",
    "🏛️ Hive SQL Data Warehouse",
    "🗺️ Kiến trúc Hệ thống & Demo"
])

# =============================================================================
# TAB 1: PHÂN TÍCH CHUYÊN SÂU & TRỰC QUAN HÓA (BATCH ANALYTICS)
# =============================================================================
with tab_analytics:
    try:
        manifest = read_manifest()
        yearly = pd.read_parquet(RESULTS_DIR / "yearly_growth.parquet").sort_values("year")
        fields = pd.read_parquet(RESULTS_DIR / "field_trends.parquet").sort_values("year")
        keywords = pd.read_parquet(RESULTS_DIR / "hot_keyword_trends.parquet").sort_values("year")
        span_years = int(manifest["max_year"]) - int(manifest["min_year"]) + 1
        group_names = sorted(fields["main_group"].dropna().unique().tolist())
        group_preview = ", ".join(group_names[:4]) + ("..." if len(group_names) > 4 else "")
        model = manifest.get("model") or {}
        if model.get("status") == "trained":
            lda_value = f"{model.get('k', '?')} Topics LDA"
            perplexity = model.get("test_log_perplexity")
            lda_desc = f"Test log-perplexity: {perplexity:.2f}" if isinstance(perplexity, (int, float)) else "Đã huấn luyện trên tập train"
        else:
            lda_value = "Chưa huấn luyện"
            lda_desc = "Chạy analyze không dùng --skip-topics"
        total_seconds = manifest.get("total_analysis_seconds")
        seconds_text = f"{total_seconds:.1f}s" if isinstance(total_seconds, (int, float)) else "Chưa ghi nhận"
        source = manifest.get("source") or {}
        shard_count = len(source.get("shards", [])) if isinstance(source.get("shards"), list) else "?"
        source_desc = f"{shard_count} shard Parquet đã tải" if shard_count != "?" else "Nguồn cục bộ đã xác minh"

        # KPI Metrics Cards
        st.markdown(f"""
        <div class="kpi-container">
            <div class="kpi-card">
                <div class="kpi-label">Tổng bài báo phân tích</div>
                <div class="kpi-value">{manifest['rows']:,}</div>
                <div class="kpi-desc">{source_desc}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Khoảng thời gian</div>
                <div class="kpi-value">{manifest['min_year']} – {manifest['max_year']}</div>
                <div class="kpi-desc">{span_years} năm nộp bài đầu tiên (v1)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Nhóm ngành khoa học</div>
                <div class="kpi-value">{manifest['groups']} Lĩnh vực</div>
                <div class="kpi-desc">{group_preview}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Mô hình phân cụm chủ đề</div>
                <div class="kpi-value">{lda_value}</div>
                <div class="kpi-desc">{lda_desc}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Thời gian phân tích Spark</div>
                <div class="kpi-value">{seconds_text}</div>
                <div class="kpi-desc">Đo bằng perf_counter trên cụm 4 cores</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">📈 Xu hướng Tăng trưởng & Diễn biến Lĩnh vực</div>', unsafe_allow_html=True)

        c_chart1, c_chart2 = st.columns([1.1, 1.2])

        with c_chart1:
            # Dual-axis Bar + Line Chart
            fig_growth = make_subplots(specs=[[{"secondary_y": True}]])
            fig_growth.add_trace(
                go.Bar(
                    x=yearly["year"],
                    y=yearly["count"],
                    name="Số bài báo",
                    marker=dict(color="#38bdf8", opacity=0.85, line=dict(color="#0284c7", width=1.5)),
                    hovertemplate="<b>Năm %{x}</b><br>Số bài: %{y:,}<extra></extra>"
                ),
                secondary_y=False
            )
            # Add YoY Growth Line
            fig_growth.add_trace(
                go.Scatter(
                    x=yearly["year"],
                    y=yearly["yoy_growth_rate"],
                    name="Tăng trưởng YoY (%)",
                    mode="lines+markers",
                    line=dict(color="#f43f5e", width=2.5),
                    marker=dict(size=6, color="#f43f5e"),
                    hovertemplate="<b>Năm %{x}</b><br>Tăng trưởng: %{y:.1f}%<extra></extra>"
                ),
                secondary_y=True
            )
            fig_growth.update_layout(
                title="<b>Số lượng bài báo & Tốc độ tăng trưởng hàng năm</b>",
                template="plotly_dark",
                paper_bgcolor="#1e293b",
                plot_bgcolor="#0f172a",
                height=380,
                margin=dict(l=40, r=40, t=50, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_growth.update_xaxes(title_text="Năm nộp bài", gridcolor="rgba(148, 163, 184, 0.1)")
            fig_growth.update_yaxes(title_text="Số bài báo", secondary_y=False, gridcolor="rgba(148, 163, 184, 0.1)")
            fig_growth.update_yaxes(title_text="Tăng trưởng (%)", secondary_y=True, gridcolor="transparent")
            st.plotly_chart(fig_growth, use_container_width=True)

        with c_chart2:
            # Area chart of the precomputed, manifest-verified percentage share.
            fields_pct = fields.copy()
            major_groups = fields_pct.groupby("main_group")["count"].sum().nlargest(8).index.tolist()
            fields_filtered = fields_pct[fields_pct["main_group"].isin(major_groups)]

            fig_fields = px.area(
                fields_filtered,
                x="year",
                y="percentage_share",
                color="main_group",
                title="<b>Tỷ trọng các lĩnh vực nghiên cứu chủ chốt (%)</b>",
                color_discrete_sequence=px.colors.qualitative.Prism,
                template="plotly_dark"
            )
            fig_fields.update_layout(
                paper_bgcolor="#1e293b",
                plot_bgcolor="#0f172a",
                height=380,
                margin=dict(l=40, r=40, t=50, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None)
            )
            fig_fields.update_xaxes(title_text="Năm", gridcolor="rgba(148, 163, 184, 0.1)")
            fig_fields.update_yaxes(title_text="Tỷ trọng (%)", gridcolor="rgba(148, 163, 184, 0.1)")
            st.plotly_chart(fig_fields, use_container_width=True)

        # Keyword Trend Explorer
        st.markdown('<div class="section-title">🔍 Khám phá Xu hướng Từ khóa Công nghệ Nóng</div>', unsafe_allow_html=True)
        available_keywords = sorted(keywords["word"].unique().tolist())
        selected_keywords = st.multiselect(
            "Chọn từ khóa để phân tích tần suất xuất hiện:",
            options=available_keywords,
            default=["transformer", "diffusion", "quantum", "neural", "deep"] if all(k in available_keywords for k in ["transformer", "diffusion", "quantum", "neural", "deep"]) else available_keywords[:5]
        )

        if selected_keywords:
            kw_filtered = keywords[keywords["word"].isin(selected_keywords)]
            fig_kw = px.line(
                kw_filtered,
                x="year",
                y="frequency",
                color="word",
                markers=True,
                title="<b>Tần suất xuất hiện của từ khóa qua các năm</b>",
                color_discrete_sequence=px.colors.qualitative.Bold,
                template="plotly_dark"
            )
            fig_kw.update_layout(
                paper_bgcolor="#1e293b",
                plot_bgcolor="#0f172a",
                height=340,
                margin=dict(l=40, r=40, t=50, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None)
            )
            fig_kw.update_xaxes(title_text="Năm", gridcolor="rgba(148, 163, 184, 0.1)")
            fig_kw.update_yaxes(title_text="Tần suất (Token counts)", gridcolor="rgba(148, 163, 184, 0.1)")
            st.plotly_chart(fig_kw, use_container_width=True)

        # Scientific Charts Gallery
        year_span = f"{manifest['min_year']}–{manifest['max_year']}"
        st.markdown(f'<div class="section-title">🎨 Thư viện 12 Biểu đồ Khoa học ({year_span})</div>', unsafe_allow_html=True)

        charts_catalog = [
            ("01_yearly_growth.png", "1. Tăng trưởng qua các năm", f"Số lượng bài báo và tốc độ tăng trưởng YoY, giai đoạn {year_span}."),
            ("02_field_trends.png", "2. Diễn biến Lĩnh vực", "Tỷ trọng các nhóm ngành theo năm; nhóm vật lý được gộp theo data contract."),
            ("03_top_categories.png", "3. Top 15 Chuyên ngành", "Các chuyên ngành có tổng số công bố lớn nhất trong tập đã tải."),
            ("04_heatmap.png", "4. Bản đồ nhiệt Mật độ", "Ma trận số bài theo từng năm và chuyên ngành hàng đầu."),
            ("05_keyword_trends.png", "5. Xu hướng Từ khóa", "Tần suất 16 từ khóa công nghệ trên 1.000 bài mỗi năm."),
            ("06_wordclouds.png", "6. Đám mây Từ khóa", "Các token abstract phổ biến nhất, tách theo nhóm ngành."),
            ("07_field_distribution.png", "7. Cơ cấu Lĩnh vực", "Tỷ lệ tổng thể giữa các nhóm ngành khoa học trong tập đã tải."),
            ("08_author_collaboration_trend.png", "8. Hợp tác Khoa học", "Số tác giả bình quân trên mỗi bài báo theo năm."),
            ("09_top_authors.png", "9. Top 20 Tác giả", "Tên tác giả xuất hiện nhiều nhất; chưa phân giải tên trùng."),
            ("10_validated_trend.png", "10. Ngoại suy Xu thế có Kiểm định", "Chỉ vẽ dự phóng tối đa 3 năm khi MAE vượt baseline holdout."),
            ("11_field_radar_comparison.png", "11. Radar So sánh Đa chiều", "So sánh quy mô, hợp tác, độ dài abstract và tăng trưởng giữa các nhóm."),
            ("12_lda_topic_bubble.png", "12. Phân cụm Chủ đề LDA", "Trọng số thuật ngữ của các chủ đề do Spark MLlib LDA huấn luyện.")
        ]

        chart_filter = st.selectbox(
            "Lọc biểu đồ chuyên đề:",
            ["Tất cả 12 biểu đồ", "Xu hướng & Tăng trưởng", "Chuyên ngành & Lĩnh vực", "Từ khóa & Chủ đề LDA", "Tác giả & Hợp tác"]
        )

        filtered_catalog = charts_catalog
        if chart_filter == "Xu hướng & Tăng trưởng":
            filtered_catalog = [c for c in charts_catalog if c[0] in ["01_yearly_growth.png", "02_field_trends.png", "10_validated_trend.png"]]
        elif chart_filter == "Chuyên ngành & Lĩnh vực":
            filtered_catalog = [c for c in charts_catalog if c[0] in ["03_top_categories.png", "04_heatmap.png", "07_field_distribution.png", "11_field_radar_comparison.png"]]
        elif chart_filter == "Từ khóa & Chủ đề LDA":
            filtered_catalog = [c for c in charts_catalog if c[0] in ["05_keyword_trends.png", "06_wordclouds.png", "12_lda_topic_bubble.png"]]
        elif chart_filter == "Tác giả & Hợp tác":
            filtered_catalog = [c for c in charts_catalog if c[0] in ["08_author_collaboration_trend.png", "09_top_authors.png"]]

        cols = st.columns(3)
        for idx, (img_name, title, desc) in enumerate(filtered_catalog):
            col_target = cols[idx % 3]
            img_path = OUTPUT_DIR / "charts" / img_name
            with col_target:
                st.markdown(f"""
                <div class="gallery-card">
                    <div class="gallery-title">{title}</div>
                    <div class="gallery-caption">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
                if img_path.exists():
                    st.image(str(img_path), use_container_width=True)
                else:
                    st.info(f"Đang đồng bộ tệp: {img_name}")

        # Data Explorer
        with st.expander("📋 Trình khám phá Dữ liệu Parquet Kết quả (Data Explorer)"):
            table_choice = st.selectbox("Chọn bảng dữ liệu kết quả:", [
                "yearly_growth.parquet (Tăng trưởng hàng năm)",
                "field_trends.parquet (Diễn biến lĩnh vực)",
                "top_categories_yearly.parquet (Top chuyên ngành theo năm)",
                "hot_keyword_trends.parquet (Tần suất từ khóa)",
                "top_authors.parquet (Top 20 tác giả)",
                "author_trends.parquet (Xu hướng số tác giả)"
            ])
            file_name = table_choice.split(" ")[0]
            target_parquet = RESULTS_DIR / file_name
            if target_parquet.exists():
                df_view = pd.read_parquet(target_parquet)
                st.caption(f"Kích thước bảng: {df_view.shape[0]:,} dòng × {df_view.shape[1]} cột")
                st.dataframe(df_view.head(100), use_container_width=True)
                csv_data = df_view.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Tải {file_name} (.csv)",
                    data=csv_data,
                    file_name=file_name.replace(".parquet", ".csv"),
                    mime="text/csv"
                )

    except (FileNotFoundError, KeyError, ValueError, RuntimeError, OSError) as exc:
        st.warning(f"⚠️ Chưa có kết quả phân tích hoặc manifest chưa được đồng bộ: {exc}")
        st.code("docker compose exec spark-jupyter python src/batch_pipeline.py all", language="shell")

# =============================================================================
# TAB 2: KAFKA INGESTION STUDIO
# =============================================================================
with tab_kafka:
    st.markdown('<div class="section-title">🚀 Thu nhận Dữ liệu Stream qua Apache Kafka</div>', unsafe_allow_html=True)
    st.info("Luồng phát dữ liệu mô phỏng bài báo mới đến Message Broker Kafka (Topic: `arxiv-papers-v2`).")

    col_single, col_replay = st.columns([1.1, 1.0])

    with col_single:
        st.markdown("#### 📝 Soạn & Gửi Bài Báo Mới (Single Producer)")
        with st.form("form_single_paper", clear_on_submit=False):
            p_id = st.text_input("ID arXiv (VD: 2401.00001 hoặc 0704.0001)", "2401.00001")
            p_title = st.text_input("Tiêu đề bài báo", "Scalable Deep Learning Architectures in Big Data Analytics")
            p_authors = st.text_input("Danh sách tác giả", "Nguyen Van A, Le Thi B, John Doe")
            p_cats = st.selectbox("Lĩnh vực chính (Categories)", [
                "cs.AI cs.LG (Trí tuệ nhân tạo & Học máy)",
                "cs.DC cs.DB (Hệ thống phân tán & CSDL)",
                "cs.CV (Thị giác máy tính)",
                "math.PR (Toán xác suất & Thống kê)",
                "quant-ph (Vật lý lượng tử)",
                "stat.ML (Thống kê máy học)"
            ])
            p_abstract = st.text_area(
                "Tóm tắt (Abstract)",
                "We present a comprehensive empirical evaluation of distributed streaming pipelines using Apache Kafka, Apache Spark, and Hadoop HDFS for high-throughput scientific paper metadata processing."
            )
            submit_paper = st.form_submit_button("🚀 Gửi bài báo vào Kafka Broker", use_container_width=True)

        if submit_paper:
            try:
                clean_cats = p_cats.split(" ")[0]
                record_payload = {
                    "id": p_id.strip(),
                    "title": p_title.strip(),
                    "authors": p_authors.strip(),
                    "categories": clean_cats,
                    "abstract": p_abstract.strip(),
                    "year": year_from_arxiv_id(p_id.strip()),
                    "timestamp": time.time()
                }
                meta = send_single_paper(record_payload, bootstrap_servers=kafka_server, topic=topic)
                st.success(f"✅ Đã gửi thành công! Kafka ACK: Topic=`{meta.topic}`, Partition=`{meta.partition}`, Offset=`{meta.offset}`")
                st.session_state.event_history.insert(0, {
                    "Thời gian": datetime.now().strftime("%H:%M:%S"),
                    "ID": p_id,
                    "Tiêu đề": p_title[:45] + "...",
                    "Partition": meta.partition,
                    "Offset": meta.offset,
                    "Trạng thái": "ACK OK"
                })
            except Exception as e:
                st.error(f"❌ Không thể gửi bài báo vào Kafka: {e}")
                st.caption("Hãy đảm bảo container Kafka đang chạy tại localhost:9092.")

    with col_replay:
        st.markdown("#### ⚡ Phát Lại Hàng Loạt (Batch Replay Simulator)")
        st.caption("Trích xuất bài báo thực tế từ Parquet và phát liên tục vào Kafka để thử nghiệm khả năng chịu tải.")

        num_replay = st.slider("Số lượng bản ghi phát lại:", min_value=5, max_value=100, value=20, step=5)

        if st.button("▶️ Khởi động Replay Stream", use_container_width=True):
            sent_count = 0
            producer = None
            try:
                records = list(sample_papers_from_local(limit=num_replay))
                producer = get_kafka_producer(kafka_server)
                prog_bar = st.progress(0.0)
                status_box = st.empty()

                for i, r in enumerate(records):
                    fut = producer.send(topic, key=r["id"], value=r)
                    res = fut.get(timeout=10)
                    sent_count += 1
                    prog_bar.progress(sent_count / len(records))
                    status_box.markdown(f"Đang gửi bài `{r['id']}` → Partition {res.partition}, Offset {res.offset}")
                    time.sleep(0.02)

                st.success(f"🎉 Hoàn thành phát lại! Đã xác nhận ACK cho **{sent_count}/{len(records)}** bài báo vào topic `{topic}`.")
            except Exception as exc:
                st.error(f"Dừng phát luồng: Đã gửi được {sent_count} bài. Lỗi: {exc}")
            finally:
                if producer is not None:
                    producer.close(timeout=3)

    # Event history log table
    st.markdown("---")
    st.markdown("#### 📜 Nhật ký Sự kiện Stream Đã Phát (Session Event Log)")
    if st.session_state.event_history:
        st.dataframe(pd.DataFrame(st.session_state.event_history), use_container_width=True)
    else:
        st.caption("Chưa có sự kiện nào được phát trong phiên hiện tại.")

# =============================================================================
# TAB 3: SPARK STREAMING & HDFS LAKEHOUSE
# =============================================================================
with tab_streaming:
    st.markdown('<div class="section-title">🌊 Spark Structured Streaming & HDFS Lakehouse</div>', unsafe_allow_html=True)

    col_stream_info, col_consumer_ctrl = st.columns([1.2, 1.0])

    with col_stream_info:
        st.markdown("""
        **Quy trình Xử lý Luồng (Real-time Pipeline):**
        1. **Consumer Engine**: Spark Structured Streaming đọc theo micro-batch từ topic `arxiv-papers-v2`.
        2. **NLP Transformer**: Làm sạch văn bản, tokenize từ khóa abstract, lọc danh sách Stopwords.
        3. **Fault Tolerance**: Lưu checkpoint vị trí đọc tại `/checkpoint/arxiv_stream_v2`.
        4. **Sink Storage**: Ghi Parquet vào HDFS, phân vùng theo `main_group_clean`: `/data/arxiv_stream_v2`.
        """)

    with col_consumer_ctrl:
        st.markdown("""
        <div style="background: rgba(30,41,59,0.8); border: 1px solid rgba(148,163,184,0.2); border-radius: 12px; padding: 14px;">
            <div style="font-weight: 600; color: #f8fafc; margin-bottom: 6px;">Lệnh Khởi động Streaming Consumer:</div>
            <code style="font-size: 0.8rem; color: #38bdf8;">docker compose --profile streaming up -d streaming-consumer</code>
            <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 8px;">
                Consumer sẽ tự động lắng nghe và nạp dữ liệu từ Kafka vào HDFS liên tục.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 📂 Trình duyệt HDFS Data Lakehouse (File Explorer)")

    hdfs_path = st.text_input("Đường dẫn HDFS:", value="/data")
    if st.button("🔄 Duyệt thư mục HDFS"):
        pass

    entries = list_hdfs_dir(hdfs_path)
    if entries:
        df_hdfs = pd.DataFrame(entries)
        # Format columns if available
        st.success(f"Đã tìm thấy {len(df_hdfs)} đối tượng trong thư mục `{hdfs_path}` trên NameNode.")
        st.dataframe(df_hdfs, use_container_width=True)
    else:
        st.info(f"Không thể đọc hoặc thư mục `{hdfs_path}` đang trống. Hãy kiểm tra trạng thái NameNode hoặc chạy consumer để tạo dữ liệu.")

# =============================================================================
# TAB 4: HIVE SQL DATA WAREHOUSE & QUERY STUDIO
# =============================================================================
with tab_hive:
    st.markdown('<div class="section-title">🏛️ Apache Hive Data Warehouse & SQL Studio</div>', unsafe_allow_html=True)
    st.caption("Truy vấn phân tích dữ liệu bài báo khoa học qua HiveServer2 Thrift Protocol (Database: `arxiv_db`).")

    col_q1, col_q2 = st.columns([1.2, 0.8])

    templates = {
        "1. Thống kê bài báo theo năm nộp": (
            "SELECT year, COUNT(*) AS paper_count\n"
            "FROM arxiv_historical\n"
            "GROUP BY year\n"
            "ORDER BY year DESC"
        ),
        "2. Top nhóm ngành có công bố nhiều nhất": (
            "SELECT main_group, COUNT(*) AS paper_count,\n"
            "       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM arxiv_historical), 2) AS percentage\n"
            "FROM arxiv_historical\n"
            "GROUP BY main_group\n"
            "ORDER BY paper_count DESC\n"
            "LIMIT 10"
        ),
        "3. Tần suất từ khóa công nghệ nóng": (
            "SELECT year, word, document_count, papers_per_1000\n"
            "FROM hot_keyword_trends\n"
            "WHERE word IN ('transformer', 'quantum', 'diffusion', 'neural')\n"
            "ORDER BY year DESC, papers_per_1000 DESC\n"
            "LIMIT 20"
        ),
        "4. Kiểm toán sự kiện Streaming trong HDFS": (
            "SELECT COUNT(*) AS total_streaming_events,\n"
            "       COUNT(DISTINCT id) AS unique_papers_received\n"
            "FROM arxiv_stream"
        ),
        "5. Danh sách bài báo mới nhất trong Data Lake": (
            "SELECT id, year, main_group, title\n"
            "FROM arxiv_historical\n"
            "LIMIT 15"
        )
    }

    with col_q1:
        chosen_template = st.selectbox("🎯 Chọn câu truy vấn phân tích mẫu:", list(templates.keys()))
        sql_input = st.text_area("Trình soạn thảo HiveQL:", templates[chosen_template], height=160)

    with col_q2:
        st.markdown("#### ⚡ Thao tác Kho dữ liệu")
        st.markdown("""
        - **MSCK REPAIR**: Cập nhật phân vùng cho cả `arxiv_historical` (theo năm) và `arxiv_stream`.
        - **Execute**: Gửi truy vấn HiveQL trực tiếp đến HiveServer2 container qua Thrift RPC.
        """)
        if st.button("🔄 Cập nhật phân vùng (MSCK REPAIR)", use_container_width=True):
            try:
                counts = refresh_all_partitions()
                st.success(
                    "✅ Đã cập nhật phân vùng: "
                    f"`arxiv_historical` = {counts['historical']:,} dòng, "
                    f"`arxiv_stream` = {counts['stream']:,} sự kiện."
                )
            except Exception as e:
                st.error(f"Lỗi cập nhật: {e}")

        run_sql = st.button("▶️ Thực thi Truy vấn SQL", use_container_width=True, type="primary")

    if run_sql:
        try:
            t_start = time.perf_counter()
            with st.spinner("Đang thực thi truy vấn trên cụm Hive..."):
                res_df = query_hive(sql_input)
            t_elapsed = time.perf_counter() - t_start
            st.success(f"✅ Hive trả về **{len(res_df):,}** dòng kết quả trong **{t_elapsed:.2f} giây**.")
            st.dataframe(res_df, use_container_width=True)

            if not res_df.empty:
                csv_bytes = res_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Xuất kết quả CSV",
                    data=csv_bytes,
                    file_name="hive_query_result.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"❌ Truy vấn Hive thất bại: {e}")
            st.info("💡 Lưu ý: Hãy đảm bảo HiveServer2 container đang chạy tại `localhost:10000`.")

# =============================================================================
# TAB 5: ARCHITECTURE & DEMO PIPELINE SNAPSHOTS
# =============================================================================
with tab_architecture:
    st.markdown('<div class="section-title">🗺️ Kiến trúc Hệ thống Phân tán & Demo Pipeline</div>', unsafe_allow_html=True)

    st.markdown("""
    Hệ thống gồm **11 dịch vụ mặc định** (12 khi bật `spark-worker-2` trong profile `full`, thêm `streaming-consumer` khi dùng profile `streaming`):
    """)

    # Container Table
    containers_data = [
        {"Container": "namenode", "Image": "hadoop-namenode:3.2.1", "Port": "9870, 9000", "Chức năng": "Quản lý siêu dữ liệu (metadata) hệ thống file HDFS"},
        {"Container": "datanode", "Image": "hadoop-datanode:3.2.1", "Port": "9864", "Chức năng": "Lưu trữ các khối dữ liệu phân tán (block storage)"},
        {"Container": "zookeeper", "Image": "cp-zookeeper:7.6.0", "Port": "2181", "Chức năng": "Quản lý trạng thái và bầu trưởng nhóm cho cụm Kafka"},
        {"Container": "kafka", "Image": "cp-kafka:7.6.0", "Port": "9092, 29092", "Chức năng": "Hàng đợi thông điệp phân tán cho dữ liệu bài báo"},
        {"Container": "spark-master", "Image": "bigdata-spark:latest", "Port": "8080, 7077", "Chức năng": "Điều phối tài nguyên tính toán và phân bổ Spark jobs"},
        {"Container": "spark-worker-1", "Image": "bigdata-spark:latest", "Port": "8081", "Chức năng": "Thực thi tính toán phân tán (2 cores, 2GB RAM)"},
        {"Container": "spark-worker-2", "Image": "bigdata-spark:latest", "Port": "8082", "Chức năng": "Worker tùy chọn (profile full): 2 cores, 2GB RAM"},
        {"Container": "spark-jupyter", "Image": "bigdata-spark:latest", "Port": "8888, 4040", "Chức năng": "Môi trường thực hành tương tác 8 Jupyter Notebooks"},
        {"Container": "hive-server", "Image": "hive:2.3.2", "Port": "10000, 10002", "Chức năng": "HiveServer2 thực thi câu lệnh SQL trên HDFS"},
        {"Container": "hive-metastore", "Image": "hive:2.3.2", "Port": "9083", "Chức năng": "Dịch vụ quản lý cấu trúc bảng và schema dữ liệu Hive"},
        {"Container": "hive-metastore-postgresql", "Image": "postgres:9.6", "Port": "5432", "Chức năng": "Cơ sở dữ liệu RDBMS lưu trữ metastore Hive"},
        {"Container": "dashboard", "Image": "python:3.11-slim", "Port": "8501", "Chức năng": "Bảng điều khiển trực quan tương tác Streamlit"}
    ]
    st.dataframe(pd.DataFrame(containers_data), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🖼️ Sơ đồ Kiến trúc Hệ thống")
    st.caption("Sơ đồ được vẽ từ cấu hình thực tế trong docker-compose.yml và src, không phải ảnh chụp màn hình.")

    screenshots_catalog = [
        ("00_pipeline_full_architecture.png", "Kiến trúc Tổng thể",
         "Luồng batch (Parquet → Spark → HDFS → Hive → Dashboard) và luồng streaming (Producer → Kafka → Spark → HDFS)."),
    ]

    s_cols = st.columns(2)
    for s_idx, (s_file, s_title, s_desc) in enumerate(screenshots_catalog):
        s_target = s_cols[s_idx % 2]
        s_path = OUTPUT_DIR / "screenshots" / s_file
        with s_target:
            st.markdown(f"""
            <div class="gallery-card">
                <div class="gallery-title">{s_title}</div>
                <div class="gallery-caption">{s_desc}</div>
            </div>
            """, unsafe_allow_html=True)
            if s_path.exists():
                st.image(str(s_path), use_container_width=True)
            else:
                st.info(f"Đang đồng bộ ảnh demo: {s_file}")

# -----------------------------------------------------------------------------
# 6. FOOTER
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.82rem; padding: 12px;">
    🌌 <b>arXiv Big Data Studio</b> — Bài tập lớn môn Xử lý Dữ liệu lớn (Big Data)<br/>
    Kết quả trong <code>output/analysis_results/</code> và báo cáo <code>output/reports/BAO_CAO_BAI_TAP_LON_BIGDATA.md</code><br/>
    Apache Spark 3.5.3 · Hadoop HDFS · Kafka · Hive · Streamlit
</div>
""", unsafe_allow_html=True)
