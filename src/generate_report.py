import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a paper-style Markdown report from existing outputs.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared region time-series CSV.")
    parser.add_argument("--quality_csv", default="data/processed/china_all_data_quality.csv", help="Data quality summary CSV.")
    parser.add_argument("--country", default="China", help="Country label.")
    parser.add_argument("--province", default="ALL", help="Province label.")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    parser.add_argument("--report_path", default="reports/report.md", help="Markdown report output path.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def fmt_number(value: object, digits: int = 3) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        if abs(float(value)) >= 1000:
            return f"{float(value):,.{digits}f}"
        return f"{float(value):.{digits}f}"
    return str(value)


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 12) -> str:
    if df.empty:
        return "暂无可用结果。"
    use = df.copy()
    if columns:
        use = use[[col for col in columns if col in use.columns]]
    use = use.head(max_rows)
    headers = list(use.columns)
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in use.iterrows():
        rows.append("| " + " | ".join(fmt_number(row[col]) for col in headers) + " |")
    return "\n".join(rows)


def figure(path: str, caption: str) -> str:
    return f"![{caption}]({path})\n\n{caption}"


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    metrics_dir = output_root / "metrics"
    prediction_dir = output_root / "predictions"
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    region_slug = slug(f"{args.country}_{args.province}")
    country_slug = slug(args.country)

    data = read_csv(Path(args.processed_csv))
    quality = read_csv(Path(args.quality_csv))
    sir_metrics = read_csv(metrics_dir / f"{region_slug}_sir_metrics.csv")
    sir_params = read_csv(metrics_dir / f"{region_slug}_sir_parameters.csv")
    tvsir_metrics = read_csv(metrics_dir / f"{region_slug}_time_varying_sir_metrics.csv")
    tvsir_params = read_csv(metrics_dir / f"{region_slug}_time_varying_sir_parameters.csv")
    ml_metrics = read_csv(metrics_dir / f"{region_slug}_ml_metrics.csv")
    compartment_ml_metrics = read_csv(metrics_dir / f"{region_slug}_compartment_ml_metrics.csv")
    province_summary = read_csv(metrics_dir / f"{country_slug}_province_trend_summary.csv")
    future_7 = read_csv(prediction_dir / f"{region_slug}_ml_future_7d.csv")
    future_14 = read_csv(prediction_dir / f"{region_slug}_ml_future_14d.csv")

    if not data.empty:
        data["date"] = pd.to_datetime(data["date"])
        start_date = data["date"].min().date().isoformat()
        end_date = data["date"].max().date().isoformat()
        days = len(data)
        final_confirmed = int(data["cumulative_confirmed"].dropna().iloc[-1])
        final_deaths = int(data["cumulative_deaths"].dropna().iloc[-1])
        final_recovered = int(data["cumulative_recovered"].dropna().iloc[-1]) if data["cumulative_recovered"].notna().any() else None
        final_recovered_text = f"{final_recovered:,}" if final_recovered is not None else "缺失"
    else:
        start_date = end_date = "未知"
        days = 0
        final_confirmed = final_deaths = 0
        final_recovered = None
        final_recovered_text = "缺失"

    top_province_text = "暂无省份汇总结果。"
    if not province_summary.empty:
        province_summary_for_report = province_summary[province_summary["province"].astype(str).str.upper() != "UNKNOWN"]
        top_province_text = markdown_table(
            province_summary_for_report,
            ["province", "final_cumulative_confirmed", "total_daily_confirmed", "peak_daily_confirmed"],
            max_rows=10,
        )

    sir_param_text = markdown_table(
        sir_params,
        ["fit_start_date", "fit_end_date", "fit_days", "beta", "gamma", "R0_beta_over_gamma", "effective_population"],
        max_rows=1,
    )
    tvsir_param_text = markdown_table(
        tvsir_params,
        ["fit_start_date", "fit_end_date", "fit_days", "mean_beta", "mean_gamma", "mean_R0_beta_over_gamma", "final_R0_beta_over_gamma"],
        max_rows=1,
    )

    model_metric_tables = []
    if not sir_metrics.empty:
        model_metric_tables.append("固定参数 SIR：\n\n" + markdown_table(sir_metrics, ["target", "model", "RMSE", "MAE", "R2"]))
    if not tvsir_metrics.empty:
        model_metric_tables.append("时变参数 SIR：\n\n" + markdown_table(tvsir_metrics, ["target", "model", "RMSE", "MAE", "R2"]))
    if not compartment_ml_metrics.empty:
        model_metric_tables.append(
            "GradientBoosting 舱室变量同窗口实验：\n\n"
            + markdown_table(compartment_ml_metrics, ["target", "model", "RMSE", "MAE", "R2", "evaluation_scope"])
        )
    if not ml_metrics.empty:
        model_metric_tables.append(
            "GradientBoosting 每日新增预测：\n\n"
            + markdown_table(ml_metrics, ["target", "model", "train_rows", "test_rows", "RMSE", "MAE", "R2"])
        )
    model_metric_text = "\n\n".join(model_metric_tables) if model_metric_tables else "暂无模型指标结果。"

    future_7_table = markdown_table(future_7, ["target", "model", "date", "forecast_day", "prediction"], max_rows=21)
    future_14_table = markdown_table(future_14, ["target", "model", "date", "forecast_day", "prediction"], max_rows=42)

    recovered_note = ""
    if not quality.empty and "possible_reset_or_stop" in quality.columns:
        recovered_quality = quality[quality["target"] == "recovered"]
        if not recovered_quality.empty and bool(recovered_quality["possible_reset_or_stop"].iloc[0]):
            reset_date = recovered_quality["terminal_zero_reset_date"].iloc[0]
            recovered_note = f"JHU recovered 序列在 {reset_date} 后存在终端归零或停止更新现象，程序将该日期后的治愈累计值视为缺失，不伪造治愈人数。"

    report = f"""# 基于传染病动力学模型与机器学习方法的疫情传播预测研究

## 摘要

本文基于 Johns Hopkins University CSSE COVID-19 全球时间序列数据，对 {args.country} 疫情传播趋势进行建模分析。研究首先将累计确诊、死亡、治愈数据转换为每日新增序列，并对负新增值进行 0 截断以处理统计回补和口径修正。随后使用固定参数 SIR、时变参数 SIR 与 GradientBoosting 回归模型分别完成舱室变量拟合、每日新增预测和未来 7 天、14 天趋势预测。实验同时补充省份层面的区域传播趋势图，用于展示不同地区之间的传播差异。

**关键词：** 疫情传播；SIR 模型；时变参数；GradientBoosting；时间序列预测；模型评价

## 一、引言

疫情数据具有明显的时间依赖性、阶段性和区域差异。传统传染病动力学模型能够解释易感者、感染者和移除者之间的转化关系，机器学习模型则更适合利用滞后项、滑动统计量和日期特征进行短期预测。本文的目标不是追求复杂模型堆叠，而是建立一个可运行、可解释、结果可复现的课程建模流程。

## 二、数据来源与预处理

数据来源为 JHU CSSE COVID-19 global time series，使用的核心文件包括累计确诊、累计死亡和累计治愈三类时间序列。本文分析区域为 {args.country}，省份参数为 {args.province}，时间范围为 {start_date} 至 {end_date}，共 {days} 天。期末累计确诊为 {final_confirmed:,}，累计死亡为 {final_deaths:,}，累计治愈为 {final_recovered_text}。

累计值转换为每日新增值时采用相邻日期差分：

```python
daily_new = cumulative.diff().fillna(cumulative.iloc[0])
daily_new = daily_new.clip(lower=0)
```

这样处理可以避免数据回补造成的负新增值直接进入模型。{recovered_note}

## 三、疫情传播规律与区域趋势分析

全国累计和每日新增趋势如下。累计曲线反映疫情总规模，每日新增 7 日均值用于减弱单日上报波动。

{figure("../outputs/figures/" + region_slug + "_cumulative_trends.png", "图 1 全国累计确诊、死亡、治愈趋势")}

{figure("../outputs/figures/" + region_slug + "_daily_trends.png", "图 2 全国每日新增确诊、死亡、治愈趋势")}

为满足区域传播趋势分析要求，本文进一步使用省份层面数据绘制各省累计确诊趋势、各省每日新增确诊趋势以及 Top 10 省份对比图。灰色线表示其他省份，彩色线突出最终累计确诊数最高的省份。JHU 数据中的 Unknown 属于未分配地区，汇总 CSV 中保留该行，但 Top 10 省份图和下表不将其作为省份排序对象。

{figure("../outputs/figures/" + country_slug + "_province_cumulative_confirmed_trends.png", "图 3 各省累计确诊趋势")}

{figure("../outputs/figures/" + country_slug + "_province_daily_confirmed_trends.png", "图 4 各省每日新增确诊 7 日均值趋势")}

{figure("../outputs/figures/" + country_slug + "_province_top10_confirmed_comparison.png", "图 5 Top 10 省份累计确诊对比")}

Top 10 省份汇总如下：

{top_province_text}

## 四、固定参数 SIR 模型

SIR 模型将人群划分为易感者 S、感染者 I 和移除者 R。本文用累计治愈人数与累计死亡人数之和近似 R，用累计确诊减去移除者近似当前感染者 I。模型方程为：

```text
dS/dt = -beta * S * I / N
dI/dt = beta * S * I / N - gamma * I
dR/dt = gamma * I
```

其中 beta 表示传播率，gamma 表示移除率，beta/gamma 可作为基本传播强度的近似指标。降低接触率会降低 beta，提高救治和隔离效率会提高 gamma，从而有助于控制传播。

固定参数 SIR 拟合参数如下：

{sir_param_text}

{figure("../outputs/figures/" + region_slug + "_sir_fit.png", "图 6 固定参数 SIR 模型拟合结果")}

## 五、时变参数 SIR 模型

固定参数 SIR 假设 beta 和 gamma 在整个窗口内不变，而真实疫情会受到检测能力、隔离政策、医疗资源和公众行为变化影响。时变参数 SIR 允许传播率和移除率随时间变化，更适合描述干预措施明显变化的阶段。

时变参数 SIR 主要参数如下：

{tvsir_param_text}

{figure("../outputs/figures/" + region_slug + "_time_varying_sir_fit.png", "图 7 时变参数 SIR 模型拟合结果")}

## 六、GradientBoosting 每日新增预测

机器学习部分使用 GradientBoostingRegressor 作为主要模型，分别预测每日新增确诊、每日新增死亡和每日新增治愈。特征包括最近 1 至 14 天及 21、28 天滞后值，3、7、14、28 日滑动均值、滑动中位数、滑动标准差、指数滑动均值、日期序号、星期和月份等。训练集与测试集按时间顺序划分，不随机打乱，避免时间序列未来信息泄露。

{figure("../outputs/figures/" + region_slug + "_confirmed_ml_test_prediction.png", "图 8 每日新增确诊测试集预测对比")}

{figure("../outputs/figures/" + region_slug + "_deaths_ml_test_prediction.png", "图 9 每日新增死亡测试集预测对比")}

{figure("../outputs/figures/" + region_slug + "_recovered_ml_test_prediction.png", "图 10 每日新增治愈测试集预测对比")}

## 七、GradientBoosting 舱室变量同窗口实验

为了让传统模型和机器学习模型在同一类舱室数据上可比，本文额外将 GradientBoosting 应用于 SIR 相同观测窗口下的 infected、removed 和 confirmed 三个变量。该实验使用同一段 SIR 观测数据构造滞后特征，并在窗口内部进行按时间顺序的训练/测试划分。

{figure("../outputs/figures/" + region_slug + "_compartment_ml_test_prediction.png", "图 11 GradientBoosting 舱室变量同窗口测试预测")}

## 八、未来 7 天和 14 天趋势预测

模型完成测试集评估后，使用最近历史值递推构造未来特征，分别输出未来 7 天和 14 天的每日新增预测。

未来 7 天预测结果：

{future_7_table}

未来 14 天预测结果：

{future_14_table}

{figure("../outputs/figures/" + region_slug + "_confirmed_ml_future_7d.png", "图 12 每日新增确诊未来 7 天预测")}

{figure("../outputs/figures/" + region_slug + "_confirmed_ml_future_14d.png", "图 13 每日新增确诊未来 14 天预测")}

## 九、模型评价与对比

本文使用 RMSE、MAE 和 R2 评价模型表现。RMSE 对较大误差更敏感，MAE 表示平均绝对偏差，R2 衡量模型相对均值基线的解释能力。如果 R2 为负，说明模型在该测试集上的效果差于直接使用均值预测，应如实保留。

{model_metric_text}

{figure("../outputs/figures/" + region_slug + "_ml_metrics_comparison.png", "图 14 GradientBoosting 每日新增预测指标对比")}

## 十、结论与不足

本文完成了从 JHU 数据读取、预处理、区域趋势分析、SIR/时变 SIR 建模、GradientBoosting 每日新增预测、未来 7 天和 14 天预测到指标输出的完整流程。固定参数 SIR 具有解释性强、参数含义明确的优点，但难以描述政策和行为变化；时变参数 SIR 对阶段性变化更敏感，但存在对数据质量和参数估计稳定性的依赖；GradientBoosting 能利用滞后特征进行短期预测，但对突发政策调整、统计口径变化和长期外推并不稳健。

本文仍存在不足：第一，JHU 数据存在回补、修正和 recovered 后期缺失问题；第二，模型未显式加入政策干预、检测能力、人口流动等外生变量；第三，机器学习模型采用递推预测，预测期越长误差越可能累积；第四，省份之间人口规模和统计口径不同，Top 10 对比只能反映原始确诊规模，不能直接等同于风险率。

## 参考文献

[1] Johns Hopkins University Center for Systems Science and Engineering. COVID-19 Data Repository.

[2] Kermack W O, McKendrick A G. A contribution to the mathematical theory of epidemics.

[3] scikit-learn developers. Gradient Boosting regression documentation.

## 附录：核心代码说明

核心流程由 `src/run_all.py` 串联完成：`prepare_data.py` 负责数据读取和预处理，`run_regional_trends.py` 负责趋势图和省份对比，`run_sir.py` 与 `run_time_varying_sir.py` 负责传统传播模型，`run_ml.py` 负责每日新增预测，`run_compartment_ml.py` 负责同窗口舱室变量实验，`generate_report.py` 负责生成本文档初稿。
"""

    report_path.write_text(report, encoding="utf-8")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
