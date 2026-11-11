"""Charts and conservative, temporally held-out trend extrapolation.

Every chart is derived from Parquet/JSON files produced by ``batch_pipeline``.
No chart contains manual observations or synthetic time series.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from project_config import RESULTS_DIR, OUTPUT_DIR, read_manifest
from batch_pipeline import save_json


def forecast_trends(keywords, manifest):
    """Compare linear extrapolation with last-value baseline on the last 3 years.

    Boundary years are excluded because a downloaded shard can contain partial years.
    Even interior years are only representative of the downloaded subset.
    """
    records, predictions = [], []
    for word in ("transformer", "attention", "diffusion", "quantum"):
        sub = keywords[(keywords.word == word) & (keywords.year > manifest["min_year"])
                       & (keywords.year < manifest["max_year"]) & (keywords.year_total >= 100)].sort_values("year")
        item = {"word": word, "status": "insufficient_history"}
        if len(sub) >= 8 and np.all(np.diff(sub.year.to_numpy()) == 1):
            x = sub.year.to_numpy(dtype=float)
            y = sub.papers_per_1000.to_numpy(dtype=float)
            origin = x[0]
            fit = np.polyfit(x[:-3] - origin, y[:-3], 1)
            heldout = np.clip(np.polyval(fit, x[-3:] - origin), 0, 1000)
            mae = float(np.mean(np.abs(y[-3:] - heldout)))
            baseline_mae = float(np.mean(np.abs(y[-3:] - y[-4])))
            item.update(train_end_year=int(x[-4]), test_years=x[-3:].astype(int).tolist(),
                        mae=mae, baseline_mae=baseline_mae, unit="papers_per_1000",
                        status="accepted" if mae < baseline_mae else "did_not_beat_baseline")
            if item["status"] == "accepted":
                fit = np.polyfit(x - origin, y, 1)
                # Only years after the dataset's last year are published as forecasts, and the
                # horizon is capped at 3 years.
                future = np.arange(int(manifest["max_year"]) + 1, int(manifest["max_year"]) + 4)
                for year, value in zip(future, np.clip(np.polyval(fit, future - origin), 0, 1000)):
                    predictions.append({"word": word, "year": int(year), "papers_per_1000": float(value)})
        records.append(item)
    return {"clean_run_id": manifest["clean_run_id"], "scope": "downloaded_subset_only",
            "method": "linear_trend_three_year_holdout_vs_last_value",
            "metrics": records}, predictions


def create_charts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud

    manifest = read_manifest()
    chart_dir = OUTPUT_DIR / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "manifest.json").unlink(missing_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    def load(name):
        path = RESULTS_DIR / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing analysis output: {path}. Run batch_pipeline.py analyze first.")
        return pd.read_parquet(path)

    def save(name, title, xlabel="", ylabel=None):
        plt.title(title + "\n(downloaded arXiv subset)", fontsize=13, fontweight="bold")
        plt.xlabel(xlabel)
        if ylabel:
            plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(chart_dir / name, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close()

    yearly = load("yearly_growth").sort_values("year")
    fields = load("field_trends")
    kw = load("hot_keyword_trends")
    cats = load("top_categories_yearly")
    terms = load("top_terms")
    authors = load("author_trends").sort_values("year")
    top_authors = load("top_authors").sort_values("count")
    field_metrics = load("field_metrics")
    group_terms = load("group_terms")

    # 01 - yearly growth
    fig, ax1 = plt.subplots(figsize=(12, 5.5))
    ax1.bar(yearly.year, yearly["count"], color="#2563eb", alpha=0.75, label="Papers")
    ax1.set_ylabel("Papers", color="#2563eb")
    ax1.tick_params(axis="y", labelcolor="#2563eb")
    ax2 = ax1.twinx()
    ax2.plot(yearly.year, yearly["yoy_growth_rate"], color="#dc2626", marker="o", linewidth=2, label="YoY growth")
    ax2.set_ylabel("YoY growth (%)", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")
    ax2.axhline(0, color="#64748b", linewidth=0.8, linestyle="--")
    last = yearly.iloc[-1]
    ax1.annotate(f"{int(last.year)}: partial year\n(boundary shard)",
                 xy=(last.year, last["count"]), xytext=(last.year - 2.9, yearly["count"].max() * 0.40),
                 fontsize=10, color="#334155",
                 arrowprops=dict(arrowstyle="->", color="#94a3b8", linewidth=1.2))
    save("01_yearly_growth.png", "Papers by first submission year and year-over-year growth",
         "First submission year")

    # 02 - field shares
    pivot = fields.pivot(index="year", columns="main_group", values="percentage_share").fillna(0).sort_index()
    pivot.plot.area(figsize=(12, 6), colormap="tab20", alpha=0.9)
    plt.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, title="Main group")
    save("02_field_trends.png", "Share of papers by main group", "First submission year", "Percent")

    # 03 - top categories
    top = cats.groupby("primary_category")["count"].sum().nlargest(15).sort_values()
    ax = top.plot.barh(figsize=(10, 6.5), color="#0f766e")
    ax.bar_label(ax.containers[0], fmt="%d", padding=3, fontsize=8)
    save("03_top_categories.png", "Top 15 primary categories in the downloaded subset", "Papers")

    # 04 - heatmap
    heat = cats[cats.primary_category.isin(top.index)].pivot(
        index="primary_category", columns="year", values="count").fillna(0)
    heat = heat.reindex(top.index)
    plt.figure(figsize=(13, 6.5))
    image = plt.imshow(heat.to_numpy(), aspect="auto", cmap="YlOrRd")
    plt.xticks(range(len(heat.columns)), heat.columns, rotation=90)
    plt.yticks(range(len(heat.index)), heat.index)
    plt.colorbar(image, label="Papers")
    save("04_heatmap.png", "Category counts by year", "First submission year")

    # 05 - keyword prevalence
    keywords_to_plot = (kw.groupby("word")["papers_per_1000"].max().nlargest(10).index.tolist())
    for required in ("transformer", "attention", "diffusion", "quantum"):
        if required in kw.word.unique() and required not in keywords_to_plot:
            keywords_to_plot.append(required)
    plt.figure(figsize=(13, 6.5))
    for word in keywords_to_plot:
        sub = kw[kw.word == word].sort_values("year")
        plt.plot(sub.year, sub.papers_per_1000, marker="o", linewidth=1.6, label=word)
    plt.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, ncol=1)
    save("05_keyword_trends.png", "Keyword document prevalence",
         "First submission year", "Papers per 1,000")

    # 06 - word clouds by main group
    main_groups = field_metrics.sort_values("papers", ascending=False).head(3)["main_group"].tolist()
    fig, axes = plt.subplots(1, len(main_groups), figsize=(16, 5.2))
    axes = np.atleast_1d(axes)
    for ax, group in zip(axes, main_groups):
        subset = group_terms[group_terms.main_group == group].nlargest(80, "count")
        frequencies = dict(zip(subset.word, subset["count"]))
        if frequencies:
            cloud = WordCloud(width=800, height=500, background_color="white", random_state=42,
                              colormap="viridis").generate_from_frequencies(frequencies)
            ax.imshow(cloud)
        ax.set_title(group)
        ax.axis("off")
    plt.suptitle("Most frequent abstract tokens by main group\n(downloaded arXiv subset)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(chart_dir / "06_wordclouds.png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close()

    # 07 - field distribution
    field_totals = fields.groupby("main_group")["count"].sum().sort_values(ascending=False)
    plt.figure(figsize=(8.5, 8.5))

    def share_label(value):
        # Tiny slices would print overlapping digits; their share is in the legend/table.
        return f"{value:.1f}%" if value >= 2 else ""

    wedges, _, autotexts = plt.pie(field_totals, autopct=share_label, startangle=90,
                                    colors=plt.cm.tab20.colors, pctdistance=0.78,
                                    textprops={"fontsize": 9})
    for text in autotexts:
        text.set_color("white")
        text.set_fontweight("bold")
    plt.legend(wedges, field_totals.index, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=9)
    save("07_field_distribution.png", "Field distribution")

    # 08 - collaboration trend
    plt.figure(figsize=(12, 5))
    plt.plot(authors.year, authors.avg_authors, marker="o", color="#7c3aed", linewidth=2)
    save("08_author_collaboration_trend.png", "Mean parsed authors per paper",
         "First submission year", "Authors")

    # 09 - top authors
    plt.figure(figsize=(12, 7))
    plt.barh(top_authors.author, top_authors["count"], color="#be123c")
    save("09_top_authors.png", "Top author names (namesakes are not disambiguated)", "Papers")

    # 10 - validated trend
    validation, predictions = forecast_trends(kw, manifest)
    save_json(OUTPUT_DIR / "forecast_validation.json", validation)
    save_json(OUTPUT_DIR / "forecast_predictions.json",
              {"clean_run_id": manifest["clean_run_id"], "predictions": predictions})
    plt.figure(figsize=(13, 6.5))
    for word in ("transformer", "attention", "diffusion", "quantum"):
        history = kw[kw.word == word].sort_values("year")
        plt.plot(history.year, history.papers_per_1000, marker="o", label=word)
        future = [r for r in predictions if r["word"] == word]
        if future:
            # Anchor the dashed forecast on the last measured year so the two lines connect.
            last = history.iloc[-1]
            plt.plot([int(last.year)] + [r["year"] for r in future],
                     [float(last.papers_per_1000)] + [r["papers_per_1000"] for r in future],
                     "--", label=word + " extrapolation")
    plt.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
    save("10_validated_trend.png", "Extrapolation only when better than held-out baseline",
         "Year", "Papers per 1,000")

    # 11 - radar comparison
    radar_metrics = [("papers", "Papers", False), ("avg_authors", "Avg authors", True),
                     ("avg_abstract_length", "Abstract length", True),
                     ("avg_token_count", "Tokens", True), ("distinct_categories", "Categories", True)]
    radar_groups = field_metrics.sort_values("papers", ascending=False).head(4)["main_group"].tolist()
    radar = field_metrics.set_index("main_group").loc[radar_groups]
    values = []
    for column, _, _ in radar_metrics:
        series = radar[column].astype(float)
        spread = series.max() - series.min()
        values.append(((series - series.min()) / spread).fillna(0).clip(0, 1) if spread > 0 else series * 0 + 0.5)
    angles = np.linspace(0, 2 * np.pi, len(radar_metrics), endpoint=False).tolist()
    angles += angles[:1]
    fig = plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)
    for index, group in enumerate(radar_groups):
        data = [float(values[j][group]) for j in range(len(radar_metrics))]
        data += data[:1]
        ax.plot(angles, data, linewidth=2, label=group)
        ax.fill(angles, data, alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([item[1] for item in radar_metrics])
    ax.set_ylim(0, 1)
    ax.set_title("Normalised comparison of major fields\n(downloaded arXiv subset)", fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.1))
    plt.tight_layout()
    plt.savefig(chart_dir / "11_field_radar_comparison.png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close()

    # 12 - LDA topic bubble
    topics_path = RESULTS_DIR / "topics.json"
    topics = json.loads(topics_path.read_text(encoding="utf-8")) if topics_path.exists() else []
    plt.figure(figsize=(12, 7))
    if topics:
        x = [float(item.get("prevalence", 0)) * 100 for item in topics]
        y = [float(np.mean(item["weights"])) for item in topics]
        sizes = [max(120, float(item.get("prevalence", 0)) * 9000) for item in topics]
        scatter = plt.scatter(x, y, s=sizes, c=range(len(topics)), cmap="viridis", alpha=0.75,
                              edgecolor="white", linewidth=1.5)
        for item, xpos, ypos in zip(topics, x, y):
            label = f"T{item['topic']}: " + ", ".join(item["terms"][:2])
            plt.annotate(label, (xpos, ypos), fontsize=7.5, xytext=(7, 5), textcoords="offset points")
        plt.colorbar(scatter, label="Topic index")
        plt.margins(x=0.30, y=0.14)
        plt.xlabel("Mean topic prevalence in sampled documents (%)")
        plt.ylabel("Mean top-term weight")
        title = "Spark MLlib LDA topics (bubble size = prevalence)"
    else:
        plt.text(0.5, 0.5, "LDA topics not trained", ha="center", va="center")
        title = "LDA topics unavailable"
    save("12_lda_topic_bubble.png", title, "Topic prevalence (%)", "Mean term weight")

    chart_files = sorted(path.name for path in chart_dir.glob("*.png"))
    if len(chart_files) != 12:
        raise RuntimeError(f"Expected 12 charts, found {len(chart_files)}: {chart_files}")
    save_json(chart_dir / "manifest.json", {
        "clean_run_id": manifest["clean_run_id"],
        "schema_version": 2,
        "charts": chart_files,
        "years": [int(manifest["min_year"]), int(manifest["max_year"])],
        "scope": manifest.get("scope"),
    })
    return validation


if __name__ == "__main__":
    print(json.dumps(create_charts(), ensure_ascii=False, indent=2))
