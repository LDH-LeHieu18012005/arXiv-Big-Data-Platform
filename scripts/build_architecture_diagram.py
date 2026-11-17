"""Draw the real architecture diagram from the project's own configuration.

Output: output/screenshots/00_pipeline_full_architecture.png
Only components that exist in docker-compose.yml / src are shown. The diagram is
deliberately word-light: the roles are described in the report text, so the labels
stay readable when the picture is printed at 15.5 cm wide.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT = BASE_DIR / "output" / "screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)

NAVY = "#0b1f3a"
BLUE = "#1d4ed8"
TEAL = "#0e9f6e"
AMBER = "#b45309"
VIOLET = "#6d28d9"
GREY = "#475569"
LIGHT = "#e8eef6"


def box(ax, x, y, w, h, title, color, text_color="white", subtitle=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.008,rounding_size=0.012",
                                linewidth=0, facecolor=color))
    offset = 0.018 if subtitle else 0.0
    ax.text(x + w / 2, y + h / 2 + offset, title, ha="center", va="center",
            fontsize=11.0, fontweight="bold", color=text_color)
    if subtitle:
        ax.text(x + w / 2, y + h / 2 - 0.032, subtitle, ha="center", va="center",
                fontsize=9.2, color=text_color, alpha=0.95)


def arrow(ax, start, end, color=GREY):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=16,
                                 linewidth=2.0, color=color,
                                 shrinkA=2, shrinkB=2))


figure, axes = plt.subplots(figsize=(10.2, 5.6), dpi=200)
axes.set_xlim(0, 1)
axes.set_ylim(0, 1)
axes.axis("off")

axes.text(0.5, 0.955, "Kiến trúc hệ thống phân tích metadata arXiv", ha="center",
          va="center", fontsize=17, fontweight="bold", color=NAVY)
axes.text(0.5, 0.902, "Hai luồng dùng chung tầng lưu trữ HDFS", ha="center",
          va="center", fontsize=10.5, color=GREY)

# Lane labels
axes.text(0.035, 0.745, "BATCH", fontsize=11, fontweight="bold", color=BLUE,
          rotation=90, va="center", ha="center")
axes.text(0.035, 0.365, "STREAM", fontsize=11, fontweight="bold", color=AMBER,
          rotation=90, va="center", ha="center")

y_batch, y_stream, height = 0.66, 0.28, 0.17
x_positions = [0.060 + index * 0.19 for index in range(5)]
width = 0.158

batch_nodes = [("Parquet nguồn", BLUE), ("Spark batch", BLUE), ("HDFS", TEAL),
               ("Hive", VIOLET), ("Dashboard", NAVY)]
stream_nodes = [("Producer", AMBER), ("Kafka", AMBER), ("Spark\nStreaming", AMBER),
                ("HDFS", TEAL), ("Hive", VIOLET)]

for x, (label, color) in zip(x_positions, batch_nodes):
    box(axes, x, y_batch, width, height, label, color)
for x, (label, color) in zip(x_positions, stream_nodes):
    box(axes, x, y_stream, width, height, label, color)

for x in x_positions[:-1]:
    arrow(axes, (x + width + 0.006, y_batch + height / 2),
          (x + 0.19 - 0.006, y_batch + height / 2), color=BLUE)
    arrow(axes, (x + width + 0.006, y_stream + height / 2),
          (x + 0.19 - 0.006, y_stream + height / 2), color=AMBER)

# Shared control chips underneath the lanes.
axes.add_patch(FancyBboxPatch((0.065, 0.075), 0.43, 0.10,
                              boxstyle="round,pad=0.008,rounding_size=0.012",
                              linewidth=0, facecolor=LIGHT))
axes.text(0.28, 0.125, "Kiểm soát chất lượng: năm nộp v1 · trùng ID · manifest",
          ha="center", va="center", fontsize=8.6, color=NAVY)
axes.add_patch(FancyBboxPatch((0.535, 0.075), 0.435, 0.10,
                              boxstyle="round,pad=0.008,rounding_size=0.012",
                              linewidth=0, facecolor=LIGHT))
axes.text(0.7525, 0.125, "Docker Compose: 11 dịch vụ mặc định\n12 khi bật profile streaming",
          ha="center", va="center", fontsize=8.4, color=NAVY, linespacing=1.15)

axes.text(0.955, 0.012,
          "Vẽ từ docker-compose.yml và src; không chứa số liệu hiệu năng hay trạng thái giả lập.",
          ha="right", va="bottom", fontsize=6.5, color=GREY)

path = OUTPUT / "00_pipeline_full_architecture.png"
figure.savefig(path, bbox_inches="tight", facecolor="white")
plt.close(figure)
print(path)
