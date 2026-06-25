# COVID-19 疫情传播模型与预测模型方法

本项目用于《计算机建模技术》期末大作业，选题为“疫情传播模型与预测模型方法”。工程围绕 JHU CSSE COVID-19 真实时间序列数据，完成数据预处理、区域传播趋势分析、SIR/时变 SIR 建模、Naive/LinearRegression/RandomForest/GradientBoosting 每日新增预测、未来 7/14 天预测、指标评价和论文式 Word 报告生成。

## 1. 项目功能

- 读取 JHU CSSE 全球累计确诊、死亡、治愈时间序列数据。
- 按国家聚合，支持指定省份；默认分析 `China Mainland`，即排除 JHU China 条目中的 `Hong Kong`、`Macau`、`Taiwan` 和 `Unknown`。
- 将累计值转换为每日新增值，并将负新增截断为 0，用于处理数据回补或统计修正。
- 生成全国累计趋势图、全国每日新增趋势图。
- 生成区域传播趋势图：各省累计确诊趋势、各省每日新增趋势、Top 10 省份累计确诊对比。
- 拟合固定参数 SIR 和时变参数 SIR 模型。
- 使用 `NaivePersistence`、`LinearRegression`、`RandomForestRegressor`、`GradientBoostingRegressor` 预测每日新增确诊、死亡、治愈。
- 在 SIR 相同窗口上补充 GradientBoosting 对 `infected`、`removed`、`confirmed` 的同窗口对比实验。
- 输出 RMSE、MAE、R2 指标、预测 CSV、图表、`reports/report.md` 和 `1030424322-解宝赛/期末大作业论文.docx`。

## 2. 环境安装

建议使用 Python 3.9 或以上版本。在项目根目录运行：

```bash
pip install -r requirements.txt
```

## 3. 数据放置

将 JHU CSSE 数据文件放到 `data/raw/`：

```text
data/raw/
├── time_series_covid19_confirmed_global.csv
├── time_series_covid19_deaths_global.csv
└── time_series_covid19_recovered_global.csv
```

当前工程已包含 China 实验所需的这三份原始数据。

## 4. 一键运行

从项目根目录运行：

```bash
python src/run_all.py --data_dir data/raw --country China --forecast_days 14 --test_ratio 0.2
```

运行完成后会生成：

- `data/processed/china_mainland_timeseries.csv`
- `data/processed/china_mainland_province_timeseries.csv`
- `outputs/figures/*.png`
- `outputs/metrics/*.csv`
- `outputs/predictions/*.csv`
- `reports/report.md`

快速验证时可以跳过省份面板：

```bash
python src/run_all.py --data_dir data/raw --country China --forecast_days 14 --test_ratio 0.2 --skip_province_panel
```

## 5. 单独运行

```bash
python src/prepare_data.py --data_dir data/raw --country China --exclude_provinces Hong Kong,Macau,Taiwan,Unknown --region_label Mainland
python src/run_regional_trends.py --processed_csv data/processed/china_mainland_timeseries.csv --province_panel_csv data/processed/china_mainland_province_timeseries.csv --country "China Mainland"
python src/run_sir.py --processed_csv data/processed/china_mainland_timeseries.csv --country China --province Mainland
python src/run_time_varying_sir.py --processed_csv data/processed/china_mainland_timeseries.csv --country China --province Mainland
python src/run_ml.py --processed_csv data/processed/china_mainland_timeseries.csv --country China --province Mainland --target all
python src/run_compartment_ml.py --processed_csv data/processed/china_mainland_timeseries.csv --country China --province Mainland
python src/generate_report.py --processed_csv data/processed/china_mainland_timeseries.csv --quality_csv data/processed/china_mainland_data_quality.csv --country China --province Mainland
```

## 6. 输出文件说明

`outputs/figures/` 中主要图表：

- `china_mainland_cumulative_trends.png`：中国大陆累计确诊、死亡、治愈趋势。
- `china_mainland_daily_trends.png`：中国大陆每日新增确诊、死亡、治愈趋势。
- `china_mainland_province_cumulative_confirmed_trends.png`：各省累计确诊趋势。
- `china_mainland_province_daily_confirmed_trends.png`：各省每日新增确诊趋势。
- `china_mainland_province_top10_confirmed_comparison.png`：Top 10 省份累计确诊对比。
- `china_mainland_sir_fit.png`：固定参数 SIR 拟合结果。
- `china_mainland_time_varying_sir_fit.png`：时变参数 SIR 历史重构结果。
- `china_mainland_compartment_ml_test_prediction.png`：GradientBoosting 舱室变量同窗口实验。
- `china_mainland_*_ml_test_prediction.png`：每日新增测试集预测对比。
- `china_mainland_*_ml_future_7d.png` 和 `china_mainland_*_ml_future_14d.png`：未来预测图。
- `china_mainland_ml_metrics_comparison.png`：每日新增预测指标对比。

`outputs/metrics/` 中主要指标：

- `metrics.csv`：综合指标表。
- `china_mainland_sir_metrics.csv`：固定参数 SIR 指标。
- `china_mainland_time_varying_sir_metrics.csv`：时变参数 SIR 描述性重构指标。
- `china_mainland_ml_metrics.csv`：每日新增预测指标，包含 Naive、LinearRegression、RandomForest、GradientBoosting。
- `china_mainland_compartment_ml_metrics.csv`：SIR 同窗口舱室变量 GradientBoosting 指标。
- `china_mainland_province_trend_summary.csv`：省份趋势汇总。

`outputs/predictions/` 中保存 SIR 拟合结果、机器学习测试集预测和未来 7/14 天预测结果。

论文式报告初稿位于：

```text
reports/report.md
reports/期末大作业论文.docx
1030424322-解宝赛/期末大作业论文.docx
```

## 7. 常见问题

1. `recovered` 后期缺失或归零怎么办？
   JHU recovered 全球序列可靠更新至 2021-08-04。程序只在该可靠区间内训练、测试 recovered；若输出 recovered 未来预测，则表示可靠区间结束后的短期外推，不代表 2023 年真实治愈趋势。

2. 为什么每日新增会把负值截断为 0？
   JHU 数据可能存在统计回补或口径修正，累计差分后会出现负新增。为保证每日新增序列可用于建模，程序将负新增截断为 0，并在报告中说明。

3. 为什么部分 R2 是负值？
   R2 为负表示模型在该测试集上的效果差于均值基线。项目会如实保存该结果，不删除、不篡改。

4. 为什么 Top 10 省份图不包含 `Unknown`？
   当前默认 `China Mainland` 口径会排除 `Hong Kong`、`Macau`、`Taiwan` 和 `Unknown`。`Unknown` 是未分配地区，不是真正省份，排除后更适合做大陆省级趋势比较。

5. 中文图表乱码怎么办？
   图表标题默认使用英文，减少不同系统缺少中文字体造成的乱码风险。报告正文为 UTF-8 编码。

6. 地区名称不匹配怎么办？
   请确认 `--country` 和 `--province` 与 JHU CSV 中的 `Country/Region`、`Province/State` 一致。默认全国聚合命令为 `--country China --province ""`。

