"""
================================================================================
🌌 arXiv Big Data Studio — Executive Analytics & Distributed Pipeline Dashboard
Kiến trúc phân tán: Kafka → Spark Streaming → HDFS Lakehouse → Hive DW → Dashboard
================================================================================
"""
import json
import base64
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

# Theme: light tech-blue design system (single source of truth).
THEME_CSS = (Path(__file__).with_name("dashboard_theme.css")).read_text(encoding="utf-8")
st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)

LOGO_PATH = Path(__file__).with_name("assets") / "cogailab_logo.svg"
if LOGO_PATH.exists():
    LOGO_B64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    LOGO_IMG = (
        f'<img src="data:image/svg+xml;base64,{LOGO_B64}" '
        'alt="CogAI Lab" style="width:100%;height:auto;display:block;"/>'
    )
else:
    LOGO_IMG = ""

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
kafka_port = kafka_port or "9092"


@st.cache_data(ttl=15, show_spinner=False)
def get_cluster_status():
    """Check the four service boundaries, cached briefly to keep reruns fast."""
    return {
        "kafka": tcp_status(kafka_host or "localhost", kafka_port),
        "spark": tcp_status(os.getenv("SPARK_MASTER_HOST", "spark-master"), 7077),
        "hdfs": check_hdfs_status().get("status") == "ONLINE",
        "hive": test_hive_connection()[0],
    }


cluster = get_cluster_status()
kafka_ok = cluster["kafka"]
spark_ok = cluster["spark"]
hdfs_is_online = cluster["hdfs"]
hive_ok = cluster["hive"]
online_count = sum(1 for value in cluster.values() if value)


def status_row(name, port, ok):
    state = "on" if ok else "off"
    label = "ONLINE" if ok else "OFFLINE"
    return (
        f'<div class="status-row"><span class="status-dot {state}"></span>'
        f'<span class="status-name">{name}</span><span class="status-port">{port}</span>'
        f'<span class="status-badge {state}">{label}</span></div>'
    )


# -----------------------------------------------------------------------------
# 3. SIDEBAR: BRAND & SERVICE HEALTH
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f'<div class="brand-logo">{LOGO_IMG}</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-sub">arXiv Big Data Demo</div>', unsafe_allow_html=True)

    st.markdown('<div class="side-label">Trạng thái dịch vụ</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="status-panel">'
        + status_row("Kafka", "9092", kafka_ok)
        + status_row("HDFS", "9870", hdfs_is_online)
        + status_row("Hive", "10000", hive_ok)
        + status_row("Spark", "7077", spark_ok)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"{online_count}/4 dịch vụ đang online")
    if st.button("Làm mới trạng thái", use_container_width=True, key="refresh_status"):
        get_cluster_status.clear()
        st.rerun()

    st.markdown('<div class="side-label">Luồng dữ liệu</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="flow-mini">
        <span>Kafka</span>
        <i>↓</i>
        <span>Spark Streaming</span>
        <i>↓</i>
        <span>HDFS</span>
        <i>↓</i>
        <span>Hive</span>
        <i>↓</i>
        <span>Dashboard</span>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. HERO: BRAND, TITLE & STACK
# -----------------------------------------------------------------------------
health_color = "#12b76a" if online_count == 4 else "#f79009"
st.markdown(f"""
<div class="hero">
    <div class="hero-brand">{LOGO_IMG}</div>
    <div class="hero-text">
        <div class="eyebrow">CogAI Lab · Big Data Demo</div>
        <h1>arXiv Big Data Platform</h1>
        <p>Thu nhận bằng Kafka, xử lý bằng Spark Streaming, lưu trên HDFS và truy vấn bằng Hive.</p>
        <div class="badge-row">
            <span class="tech-badge spark">Apache Spark</span>
            <span class="tech-badge kafka">Apache Kafka</span>
            <span class="tech-badge hdfs">Hadoop HDFS</span>
            <span class="tech-badge hive">Apache Hive</span>
            <span class="tech-badge" style="color:{health_color}; border-color:{health_color}55; background:#ffffff;">● {online_count}/4 dịch vụ online</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. MAIN NAVIGATION
#    Only the active section is rendered, and ?tab=<slug> opens a section directly
#    (handy when demoing: /?tab=hive jumps straight to the SQL studio).
# -----------------------------------------------------------------------------
NAV_ITEMS = {
    "overview": "Tổng quan",
    "ingest": "Gửi dữ liệu",
    "pipeline": "Xử lý & HDFS",
    "hive": "Hive SQL",
    "architecture": "Kiến trúc",
}
def _normalise_tab(value) -> str:
    slug = str(value or "").strip().lower()
    return slug if slug in NAV_ITEMS else "overview"


requested_tab = _normalise_tab(st.query_params.get("tab"))

# The URL wins only when it changes from outside the widget (deep link, Back/Forward).
# When the user clicks a tab the widget state is already ahead of the URL, so we keep it.
if st.session_state.get("_nav_url_tab") != requested_tab or "main_nav" not in st.session_state:
    st.session_state["main_nav"] = NAV_ITEMS[requested_tab]

_selected_tab = st.segmented_control(
    "Điều hướng",
    options=list(NAV_ITEMS.values()),
    key="main_nav",
    label_visibility="collapsed",
)
if not _selected_tab:
    _selected_tab = NAV_ITEMS[requested_tab]

_active_tab = next(slug for slug, label in NAV_ITEMS.items() if label == _selected_tab)
st.session_state["_nav_url_tab"] = _active_tab
if _normalise_tab(st.query_params.get("tab")) != _active_tab:
    st.query_params["tab"] = _active_tab
if _active_tab != "hive":
    # Deep-link helpers only belong to the Hive tab; do not leak them to other sections.
    for _stale_param in ("q", "auto"):
        if _stale_param in st.query_params:
            del st.query_params[_stale_param]

show_overview = _selected_tab == NAV_ITEMS["overview"]
show_ingest = _selected_tab == NAV_ITEMS["ingest"]
show_pipeline = _selected_tab == NAV_ITEMS["pipeline"]
show_hive = _selected_tab == NAV_ITEMS["hive"]
show_architecture = _selected_tab == NAV_ITEMS["architecture"]

# =============================================================================
# SECTION 1: TỔNG QUAN — PHÂN TÍCH BATCH & TRỰC QUAN HÓA
# =============================================================================
if show_overview:
    try:
        manifest = read_manifest()
        yearly = pd.read_parquet(RESULTS_DIR / "yearly_growth.parquet").sort_values("year")
        fields = pd.read_parquet(RESULTS_DIR / "field_trends.parquet")
        span_years = int(manifest["max_year"]) - int(manifest["min_year"]) + 1
        group_names = sorted(fields["main_group"].dropna().unique().tolist())
        group_preview = ", ".join(group_names[:4]) + ("..." if len(group_names) > 4 else "")
        model = manifest.get("model") or {}
        if model.get("status") == "trained":
            lda_desc = (
                f"Test log-perplexity {model['test_log_perplexity']:.2f}"
                if isinstance(model.get("test_log_perplexity"), (int, float))
                else "Đã huấn luyện trên tập train"
            )
        else:
            lda_desc = "Chưa huấn luyện"

        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi">
                <div class="kpi-top"><span class="kpi-label">Tổng bài báo</span><span class="kpi-icon">Σ</span></div>
                <div class="kpi-value">{manifest['rows']:,}</div>
                <div class="kpi-hint">đã xử lý bằng Spark</div>
            </div>
            <div class="kpi violet">
                <div class="kpi-top"><span class="kpi-label">Giai đoạn</span><span class="kpi-icon">◷</span></div>
                <div class="kpi-value">{manifest['min_year']}–{manifest['max_year']}</div>
                <div class="kpi-hint">{span_years} năm nộp bản v1</div>
            </div>
            <div class="kpi green">
                <div class="kpi-top"><span class="kpi-label">Nhóm ngành</span><span class="kpi-icon">◈</span></div>
                <div class="kpi-value">{manifest['groups']}</div>
                <div class="kpi-hint">{group_preview}</div>
            </div>
            <div class="kpi amber">
                <div class="kpi-top"><span class="kpi-label">Chủ đề LDA</span><span class="kpi-icon">◇</span></div>
                <div class="kpi-value">{model.get('k', '—')} topics</div>
                <div class="kpi-hint">{lda_desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="section-head">
            <span class="section-num">01</span>
            <div>
                <h2>Bức tranh dữ liệu</h2>
                <p>Chỉ giữ hai biểu đồ chính: số bài theo năm và quy mô từng nhóm ngành.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c_chart1, c_chart2 = st.columns([1.1, 1.0])

        with c_chart1:
            st.markdown(
                '<div class="chart-title">Số bài báo theo năm</div>'
                '<div class="chart-sub">Cột: số bài · Đường: tăng trưởng so với năm trước</div>',
                unsafe_allow_html=True,
            )
            fig_growth = make_subplots(specs=[[{"secondary_y": True}]])
            fig_growth.add_trace(
                go.Bar(
                    x=yearly["year"],
                    y=yearly["count"],
                    name="Số bài",
                    marker=dict(color="#1a6cf0", opacity=0.9, line=dict(width=0)),
                    hovertemplate="<b>Năm %{x}</b><br>Số bài: %{y:,}<extra></extra>",
                ),
                secondary_y=False,
            )
            fig_growth.add_trace(
                go.Scatter(
                    x=yearly["year"],
                    y=yearly["yoy_growth_rate"],
                    name="Tăng trưởng YoY",
                    mode="lines+markers",
                    line=dict(color="#f79009", width=2.4),
                    marker=dict(size=6, color="#f79009"),
                    hovertemplate="<b>Năm %{x}</b><br>Tăng trưởng: %{y:.1f}%<extra></extra>",
                ),
                secondary_y=True,
            )
            fig_growth.update_layout(
                template="plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", color="#33547a", size=11),
                height=330,
                margin=dict(l=8, r=8, t=30, b=8),
                bargap=0.4,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0, title=None, font=dict(size=10)),
            )
            fig_growth.update_xaxes(title_text=None, gridcolor="#e6eef8", zeroline=False)
            fig_growth.update_yaxes(title_text="Số bài", secondary_y=False, gridcolor="#e6eef8", zeroline=False)
            fig_growth.update_yaxes(title_text="Tăng trưởng (%)", secondary_y=True, showgrid=False, zeroline=False)
            st.plotly_chart(fig_growth, use_container_width=True, config={"displayModeBar": False})

        with c_chart2:
            st.markdown(
                '<div class="chart-title">Quy mô theo nhóm ngành</div>'
                '<div class="chart-sub">Tổng số bài của từng nhóm trong toàn bộ giai đoạn</div>',
                unsafe_allow_html=True,
            )
            group_totals = (
                fields.groupby("main_group", as_index=False)["count"].sum().sort_values("count")
            )
            fig_groups = px.bar(
                group_totals,
                x="count",
                y="main_group",
                orientation="h",
                template="plotly_white",
                color_discrete_sequence=["#1a6cf0"],
            )
            fig_groups.update_traces(
                marker_line_width=0,
                hovertemplate="<b>%{y}</b><br>%{x:,} bài<extra></extra>",
            )
            fig_groups.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", color="#33547a", size=11),
                height=330,
                margin=dict(l=8, r=12, t=30, b=8),
                showlegend=False,
                bargap=0.35,
            )
            fig_groups.update_xaxes(title_text="Số bài", gridcolor="#e6eef8", zeroline=False)
            fig_groups.update_yaxes(title_text=None, gridcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_groups, use_container_width=True, config={"displayModeBar": False})

        total_rows = int(manifest["rows"])
        top_group = group_totals.iloc[-1]
        top_share = (top_group["count"] / total_rows * 100) if total_rows else 0
        last_year = int(manifest["max_year"])
        last_year_rows = yearly[yearly["year"] == last_year]
        last_count = int(last_year_rows["count"].iloc[0]) if not last_year_rows.empty else 0

        st.markdown("""
        <div class="section-head">
            <span class="section-num">02</span>
            <div>
                <h2>Ba điểm chính để trình bày</h2>
                <p>Đủ ngắn để nói trong một phút khi demo.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="insight-grid">
            <div class="insight">
                <div class="insight-title">Pipeline rõ ràng</div>
                <div class="insight-text">Parquet → Spark → HDFS → Hive → Dashboard.
                Cùng một nguồn dữ liệu, chạy được cả batch và streaming.</div>
            </div>
            <div class="insight green">
                <div class="insight-title">{top_group['main_group']} dẫn đầu</div>
                <div class="insight-text">Chiếm <b>{top_share:.0f}%</b> tổng số bài
                ({int(top_group['count']):,} bài), cho thấy dữ liệu tập trung ở nhóm ngành này.</div>
            </div>
            <div class="insight amber">
                <div class="insight-title">Lưu ý năm {last_year}</div>
                <div class="insight-text">Chỉ có <b>{last_count:,} bài</b> vì phạm vi dữ liệu dừng ở
                {last_year} (bản trích xuất 2 shard). Mức giảm cuối biểu đồ phản ánh giới hạn
                phạm vi, không phải xu hướng thật của ngành.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    except (FileNotFoundError, KeyError, ValueError, RuntimeError, OSError) as exc:
        st.warning(f"Chưa có kết quả phân tích hoặc manifest chưa được đồng bộ: {exc}")
        st.code("docker compose exec spark-jupyter python src/batch_pipeline.py all", language="shell")


# =============================================================================
# SECTION 2: GỬI DỮ LIỆU — KAFKA INGESTION STUDIO
# =============================================================================
if show_ingest:
    st.markdown(f"""
    <div class="section-head">
        <span class="section-num">KAFKA</span>
        <div>
            <h2>Thu nhận dữ liệu stream</h2>
            <p>Producer gửi bài báo mới vào topic <b>{topic}</b>, sau đó Spark Streaming tiêu thụ và ghi xuống HDFS.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_single, col_replay = st.columns([1.15, 1.0])

    with col_single:
        st.markdown('<div class="chart-title">Gửi một bài báo mới</div><div class="chart-sub">Dữ liệu vào Kafka rồi đi tiếp sang Hive sau khi streaming xử lý.</div>', unsafe_allow_html=True)
        with st.form("form_single_paper", clear_on_submit=False):
            p_id = st.text_input("ID arXiv", "2401.00001", help="Ví dụ: 2401.00001 hoặc 0704.0001")
            p_title = st.text_input("Tiêu đề", "Scalable Deep Learning Architectures in Big Data Analytics")
            p_authors = st.text_input("Tác giả", "Nguyen Van A, Le Thi B, John Doe")
            p_cats = st.selectbox("Lĩnh vực", [
                "cs.AI cs.LG (Trí tuệ nhân tạo & Học máy)",
                "cs.DC cs.DB (Hệ thống phân tán & CSDL)",
                "cs.CV (Thị giác máy tính)",
                "math.PR (Toán xác suất & Thống kê)",
                "quant-ph (Vật lý lượng tử)",
                "stat.ML (Thống kê máy học)"
            ])
            p_abstract = st.text_area(
                "Tóm tắt",
                "We present a comprehensive empirical evaluation of distributed streaming pipelines using Apache Kafka, Apache Spark, and Hadoop HDFS for high-throughput scientific paper metadata processing.",
                height=110
            )
            submit_paper = st.form_submit_button("Gửi vào Kafka", use_container_width=True, type="primary")

        if submit_paper:
            try:
                clean_cats = p_cats.split("(")[0].strip()
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
                st.success(
                    f"Đã gửi thành công. Topic `{meta.topic}` · Partition `{meta.partition}` · Offset `{meta.offset}`."
                )
                st.caption("Xem bài vừa gửi tại tab **Hive SQL → mẫu 6. Bài báo streaming mới nhất** (sau khi consumer xử lý xong).")
                st.session_state.event_history.insert(0, {
                    "Thời gian": datetime.now().strftime("%H:%M:%S"),
                    "ID": p_id,
                    "Tiêu đề": p_title[:45] + "...",
                    "Partition": meta.partition,
                    "Offset": meta.offset,
                    "Trạng thái": "ACK OK"
                })
            except Exception as e:
                st.error(f"Không thể gửi bài báo vào Kafka: {e}")
                st.caption("Kiểm tra container Kafka tại `localhost:9092`.")

    with col_replay:
        st.markdown('<div class="chart-title">Phát lại hàng loạt</div><div class="chart-sub">Lấy bài báo thực tế từ Parquet và bắn liên tục vào Kafka để thử tải.</div>', unsafe_allow_html=True)
        num_replay = st.slider("Số bản ghi phát lại", min_value=5, max_value=100, value=20, step=5)

        if st.button("Khởi động replay", use_container_width=True):
            sent_count = 0
            producer = None
            replay_history = []
            try:
                records = list(sample_papers_from_local(limit=num_replay))
                producer = get_kafka_producer(kafka_server)
                prog_bar = st.progress(0.0)
                status_box = st.empty()

                for r in records:
                    fut = producer.send(topic, key=r["id"], value=r)
                    res = fut.get(timeout=10)
                    sent_count += 1
                    prog_bar.progress(sent_count / len(records))
                    status_box.markdown(f"`{r['id']}` → Partition {res.partition}, Offset {res.offset}")
                    replay_history.append({
                        "Thời gian": datetime.now().strftime("%H:%M:%S"),
                        "ID": r["id"],
                        "Tiêu đề": (r.get("title") or "")[:45] + "...",
                        "Partition": res.partition,
                        "Offset": res.offset,
                        "Trạng thái": "ACK OK",
                    })
                    time.sleep(0.02)

                st.success(f"Đã xác nhận ACK cho **{sent_count}/{len(records)}** bài vào topic `{topic}`.")
            except Exception as exc:
                st.error(f"Dừng phát luồng sau {sent_count} bài: {exc}")
            finally:
                if replay_history:
                    st.session_state.event_history = (
                        replay_history[::-1] + st.session_state.event_history
                    )[:50]
                if producer is not None:
                    producer.close(timeout=3)

    st.markdown("""
    <div class="section-head">
        <span class="section-num">LOG</span>
        <div>
            <h2>Nhật ký phiên hiện tại</h2>
            <p>Các sự kiện đã phát thành công trong phiên làm việc này.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.session_state.event_history:
        st.dataframe(pd.DataFrame(st.session_state.event_history), use_container_width=True, hide_index=True)
    else:
        st.caption("Chưa có sự kiện nào được phát trong phiên hiện tại.")

# =============================================================================
# SECTION 3: XỬ LÝ & HDFS — SPARK STREAMING LAKEHOUSE
# =============================================================================
if show_pipeline:
    st.markdown("""
    <div class="section-head">
        <span class="section-num">STREAM</span>
        <div>
            <h2>Spark Structured Streaming &amp; HDFS Lakehouse</h2>
            <p>Bốn bước từ Kafka đến bảng Hive, kèm trình duyệt dữ liệu trên HDFS.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="pipeline">
        <div class="pipe-step">
            <div class="pipe-num">01</div>
            <div class="pipe-title">Consumer Engine</div>
            <div class="pipe-desc">Spark Structured Streaming đọc micro-batch từ topic <b>arxiv-papers-v2</b>.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">02</div>
            <div class="pipe-title">NLP Transformer</div>
            <div class="pipe-desc">Làm sạch văn bản, tokenize abstract và loại bỏ stopwords.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">03</div>
            <div class="pipe-title">Fault Tolerance</div>
            <div class="pipe-desc">Checkpoint vị trí đọc tại <b>/checkpoint/arxiv_stream_v2</b>.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">04</div>
            <div class="pipe-title">Sink Storage</div>
            <div class="pipe-desc">Ghi Parquet vào HDFS, phân vùng theo <b>main_group_clean</b>.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="code-box">
        <div class="code-box-label">Lệnh khởi động streaming consumer</div>
        <code>docker compose --profile streaming up -d streaming-consumer</code>
        <div class="code-box-note">Consumer lắng nghe Kafka và nạp dữ liệu vào HDFS liên tục. Dữ liệu sau đó được bảng Hive <b>arxiv_stream</b> đọc trực tiếp.</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="section-head">
        <span class="section-num">HDFS</span>
        <div>
            <h2>Trình duyệt Data Lakehouse</h2>
            <p>Chỉ tải lại khi bạn bấm nút, để dashboard không bị chậm sau mỗi thao tác.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "hdfs_entries" not in st.session_state:
        st.session_state.hdfs_entries = {}
    if "hdfs_path" not in st.session_state:
        st.session_state.hdfs_path = "/data"

    col_path, col_btn = st.columns([3, 1])
    with col_path:
        hdfs_path = st.text_input("Đường dẫn HDFS", value=st.session_state.hdfs_path, label_visibility="collapsed", placeholder="/data")
    with col_btn:
        load_hdfs = st.button("Duyệt thư mục", use_container_width=True)

    if load_hdfs or hdfs_path not in st.session_state.hdfs_entries:
        with st.spinner("Đang đọc NameNode..."):
            st.session_state.hdfs_entries[hdfs_path] = list_hdfs_dir(hdfs_path)
        st.session_state.hdfs_path = hdfs_path

    entries = st.session_state.hdfs_entries.get(hdfs_path)
    if entries:
        def human_size(value):
            try:
                size = float(value)
            except (TypeError, ValueError):
                return "—"
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if size < 1024 or unit == "TB":
                    return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        df_raw = pd.DataFrame(entries)
        df_view = pd.DataFrame({
            "Tên": df_raw.get("pathSuffix", ""),
            "Loại": df_raw.get("type", "").map(lambda t: "Thư mục" if t == "DIRECTORY" else "Tệp"),
            "Kích thước": [
                "—" if t == "DIRECTORY" else human_size(size)
                for t, size in zip(df_raw.get("type", ""), df_raw.get("length", 0))
            ],
            "Sửa đổi": pd.to_datetime(df_raw.get("modificationTime", 0), unit="ms").dt.strftime("%d/%m/%Y %H:%M"),
            "Chủ sở hữu": df_raw.get("owner", ""),
            "Quyền": df_raw.get("permission", ""),
        })
        st.markdown(
            f'<div class="result-bar"><span class="result-chip">Thư mục <strong>{hdfs_path}</strong></span>'
            f'<span class="result-chip"><strong>{len(df_view)}</strong> đối tượng</span></div>',
            unsafe_allow_html=True,
        )
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        st.caption("Muốn xem nội dung bản ghi, dùng tab **Hive SQL** — Hive đọc trực tiếp cùng dữ liệu Parquet này.")
    else:
        st.info(f"Không đọc được hoặc thư mục `{hdfs_path}` đang trống. Kiểm tra NameNode hoặc chạy consumer để tạo dữ liệu.")

# =============================================================================
# SECTION 4: HIVE SQL — DATA WAREHOUSE & QUERY STUDIO
# =============================================================================
if show_hive:
    st.markdown("""
    <div class="section-head">
        <span class="section-num">HIVE</span>
        <div>
            <h2>SQL Warehouse</h2>
            <p>Truy vấn trực tiếp <b>arxiv_db</b> qua HiveServer2 Thrift. Kết quả được giữ lại khi thao tác tiếp.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    templates = {
        "1. Thống kê bài báo theo năm nộp": (
            "SELECT year, COUNT(*) AS paper_count\n"
            "FROM arxiv_historical\n"
            "GROUP BY year\n"
            "ORDER BY year DESC"
        ),
        "2. Top nhóm ngành có công bố nhiều nhất": (
            "SELECT main_group, paper_count,\n"
            "       ROUND(paper_count * 100.0 / SUM(paper_count) OVER (), 2) AS percentage\n"
            "FROM (SELECT main_group, COUNT(*) AS paper_count\n"
            "      FROM arxiv_historical GROUP BY main_group) g\n"
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
        ),
        "6. Bài báo streaming mới nhất (xem bài vừa gửi)": (
            "SELECT id, title, year, main_group_clean, processed_time\n"
            "FROM arxiv_stream\n"
            "ORDER BY processed_time DESC, id DESC\n"
            "LIMIT 20"
        ),
        "7. So sánh mẫu: raw vs clean vs tokens": (
            "SELECT id, main_group_clean, year,\n"
            "       LENGTH(abstract) AS raw_chars,\n"
            "       LENGTH(clean_abstract) AS clean_chars,\n"
            "       SIZE(abstract_tokens) AS token_count,\n"
            "       processed_time\n"
            "FROM arxiv_stream\n"
            "ORDER BY processed_time DESC, id DESC\n"
            "LIMIT 12"
        ),
        "8. Phân bố sự kiện theo nhóm ngành": (
            "SELECT main_group_clean, COUNT(*) AS events,\n"
            "       COUNT(DISTINCT id) AS papers,\n"
            "       ROUND(AVG(SIZE(abstract_tokens)), 1) AS avg_tokens,\n"
            "       ROUND(AVG(LENGTH(clean_abstract)), 0) AS avg_clean_chars\n"
            "FROM arxiv_stream\n"
            "GROUP BY main_group_clean\n"
            "ORDER BY events DESC"
        ),
    }

    col_q1, col_q2 = st.columns([1.35, 0.65])

    # Deep link helper: ?tab=hive&q=7 preselects template 7, &auto=1 runs it once.
    template_names = list(templates.keys())
    preset_index = 0
    template_param = str(st.query_params.get("q", "")).strip()
    if template_param:
        for idx, name in enumerate(template_names):
            if name.split(".")[0].strip() == template_param:
                preset_index = idx
                break

    with col_q1:
        chosen_template = st.selectbox("Mẫu truy vấn", template_names, index=preset_index)
        sql_input = st.text_area(
            "HiveQL",
            templates[chosen_template],
            height=175,
            key=f"hive_sql_{chosen_template}",
        )

    with col_q2:
        st.markdown('<div class="chart-title">Thao tác kho dữ liệu</div><div class="chart-sub">Cập nhật phân vùng rồi thực thi truy vấn.</div>', unsafe_allow_html=True)
        refresh_clicked = st.button("Cập nhật phân vùng (MSCK REPAIR)", use_container_width=True, key="hive_refresh_btn")
        run_sql = st.button("Thực thi truy vấn", use_container_width=True, type="primary", key="hive_run_btn")

        if refresh_clicked:
            try:
                st.session_state.hive_refresh = {"ok": True, "counts": refresh_all_partitions()}
            except Exception as e:
                st.session_state.hive_refresh = {"ok": False, "error": str(e)}

        refresh_state = st.session_state.get("hive_refresh")
        if refresh_state:
            if refresh_state["ok"]:
                c = refresh_state["counts"]
                st.success(
                    f"Đã cập nhật phân vùng: `arxiv_historical` = {c['historical']:,} dòng, "
                    f"`arxiv_stream` = {c['stream']:,} sự kiện."
                )
            else:
                st.error(f"Lỗi cập nhật phân vùng: {refresh_state['error']}")

        st.markdown(
            '<div class="code-box-note" style="margin-top:10px;">'
            'Mẫu <b>6</b> hiển thị các bài vừa gửi qua Kafka. Nếu chưa thấy, kiểm tra '
            'container <b>streaming-consumer</b> đang chạy.</div>',
            unsafe_allow_html=True,
        )

    auto_run = st.query_params.get("auto") == "1" and not st.session_state.get("hive_auto_ran")
    if auto_run:
        st.session_state.hive_auto_ran = True

    if run_sql or auto_run:
        # Clear any previous result so a slow query never shows stale rows.
        st.session_state.hive_result = None
        st.session_state.hive_meta = None
        st.session_state.hive_error = None
        try:
            t_start = time.perf_counter()
            with st.spinner("Đang thực thi trên HiveServer2..."):
                res_df = query_hive(sql_input)
            elapsed = time.perf_counter() - t_start
            st.session_state.hive_result = res_df
            st.session_state.hive_meta = {"rows": len(res_df), "seconds": elapsed, "sql": sql_input}
            st.session_state.hive_error = None
        except Exception as e:
            st.session_state.hive_result = None
            st.session_state.hive_error = str(e)

    if st.session_state.get("hive_error"):
        st.error(f"Truy vấn thất bại: {st.session_state.hive_error}")
        st.caption("Kiểm tra HiveServer2 tại `localhost:10000` hoặc chạy MSCK REPAIR nếu bảng chưa thấy dữ liệu.")

    res_df = st.session_state.get("hive_result")
    if res_df is not None:
        meta = st.session_state.get("hive_meta", {})
        st.markdown(
            f'<div class="result-bar">'
            f'<span class="result-chip"><strong>{meta.get("rows", len(res_df)):,}</strong> dòng</span>'
            f'<span class="result-chip"><strong>{meta.get("seconds", 0):.2f}s</strong> thời gian</span>'
            f'<span class="result-chip"><strong>{res_df.shape[1] if not res_df.empty else 0}</strong> cột</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if res_df.empty:
            st.caption("Truy vấn chạy thành công nhưng không có dòng nào trả về.")
        else:
            display_df = res_df.copy()
            if "year" in display_df.columns:
                display_df["year"] = display_df["year"].apply(
                    lambda v: str(int(v)) if pd.notna(v) and str(v).strip().lstrip("-").isdigit() else v
                )
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.download_button(
                label="Xuất kết quả CSV",
                data=res_df.to_csv(index=False).encode("utf-8"),
                file_name="hive_query_result.csv",
                mime="text/csv",
                key="hive_download_btn",
            )

# =============================================================================
# SECTION 5: KIẾN TRÚC — ARCHITECTURE & DEMO PIPELINE
# =============================================================================
if show_architecture:
    st.markdown("""
    <div class="section-head">
        <span class="section-num">ARCH</span>
        <div>
            <h2>Kiến trúc &amp; luồng dữ liệu</h2>
            <p>Năm tầng, chạy trong 12 container Docker trên cùng một máy.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="pipeline five">
        <div class="pipe-step">
            <div class="pipe-num">01 · NGUỒN</div>
            <div class="pipe-title">Dữ liệu arXiv</div>
            <div class="pipe-desc">Parquet đã tải sẵn, hơn 700 nghìn bài báo.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">02 · XỬ LÝ</div>
            <div class="pipe-title">Apache Spark</div>
            <div class="pipe-desc">Batch phân tích và streaming tiêu thụ Kafka.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">03 · LƯU TRỮ</div>
            <div class="pipe-title">Hadoop HDFS</div>
            <div class="pipe-desc">Data Lakehouse, phân vùng theo nhóm ngành.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">04 · TRUY VẤN</div>
            <div class="pipe-title">Apache Hive</div>
            <div class="pipe-desc">SQL trên HDFS qua HiveServer2.</div>
        </div>
        <div class="pipe-step">
            <div class="pipe-num">05 · HIỂN THỊ</div>
            <div class="pipe-title">Streamlit</div>
            <div class="pipe-desc">Dashboard tương tác cho demo.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="side-label">Mở giao diện dịch vụ</div>', unsafe_allow_html=True)
    l1, l2, l3, l4 = st.columns(4)
    with l1:
        st.link_button("Spark UI", "http://localhost:8080", use_container_width=True)
    with l2:
        st.link_button("HDFS UI", "http://localhost:9870", use_container_width=True)
    with l3:
        st.link_button("JupyterLab", "http://localhost:8888", use_container_width=True)
    with l4:
        st.link_button("Hive Web", "http://localhost:10002", use_container_width=True)

    containers_data = [
        {"Container": "namenode", "Image": "hadoop-namenode:3.2.1", "Port": "9870, 9000", "Chức năng": "Quản lý metadata HDFS"},
        {"Container": "datanode", "Image": "hadoop-datanode:3.2.1", "Port": "9864", "Chức năng": "Lưu trữ block dữ liệu"},
        {"Container": "zookeeper", "Image": "cp-zookeeper:7.6.0", "Port": "2181", "Chức năng": "Điều phối cụm Kafka"},
        {"Container": "kafka", "Image": "cp-kafka:7.6.0", "Port": "9092, 29092", "Chức năng": "Hàng đợi thông điệp"},
        {"Container": "spark-master", "Image": "bigdata-spark:latest", "Port": "8080, 7077", "Chức năng": "Điều phối Spark jobs"},
        {"Container": "spark-worker-1", "Image": "bigdata-spark:latest", "Port": "8081", "Chức năng": "Tính toán phân tán (2 cores)"},
        {"Container": "spark-worker-2", "Image": "bigdata-spark:latest", "Port": "8082", "Chức năng": "Worker tùy chọn (profile full)"},
        {"Container": "spark-jupyter", "Image": "bigdata-spark:latest", "Port": "8888, 4040", "Chức năng": "Notebook thực hành"},
        {"Container": "hive-server", "Image": "hive:2.3.2", "Port": "10000, 10002", "Chức năng": "HiveServer2 - SQL trên HDFS"},
        {"Container": "hive-metastore", "Image": "hive:2.3.2", "Port": "9083", "Chức năng": "Quản lý schema bảng"},
        {"Container": "hive-metastore-postgresql", "Image": "postgres:9.6", "Port": "5432", "Chức năng": "Lưu metastore"},
        {"Container": "dashboard", "Image": "python:3.11-slim", "Port": "8501", "Chức năng": "Dashboard Streamlit"},
    ]
    with st.expander("Chi tiết 12 container"):
        st.dataframe(pd.DataFrame(containers_data), use_container_width=True, hide_index=True)

    s_path = OUTPUT_DIR / "screenshots" / "00_pipeline_full_architecture.png"
    with st.expander("Sơ đồ kiến trúc chi tiết"):
        if s_path.exists():
            st.image(str(s_path), use_container_width=True)
        else:
            st.info("Đang đồng bộ ảnh kiến trúc: 00_pipeline_full_architecture.png")

# -----------------------------------------------------------------------------
# 6. FOOTER
# -----------------------------------------------------------------------------
st.markdown("""
<div class="app-footer">
    <b>CogAI Lab</b> · arXiv Big Data Demo<br/>
    Kafka → Spark Streaming → HDFS → Hive → Streamlit
</div>
""", unsafe_allow_html=True)

