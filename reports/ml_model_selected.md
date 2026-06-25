# Selected Machine Learning Model

## 调整原因

本项目的课程主题是“疫情传播模型与预测模型方法”。在当前阶段，机器学习模型不再作为论文主线，而作为传统传染病动力学模型的预测对照。为了避免结果部分过于分散，最终机器学习实验只保留一个综合表现较好的模型。

## 保留模型

根据已有测试集结果，排除 `RollingMean7` 这种简单滑动平均基线后，`GradientBoostingRegressor` 在每日新增确诊、每日新增死亡和每日新增治愈三个任务上的综合表现较稳。因此主实验保留：

- `GradientBoostingRegressor`

代码中仍然保留 `LinearRegression`、`RandomForest`、`ExtraTrees` 等候选模型，方便后续补充实验；但默认运行只输出 `GradientBoosting` 的指标、预测结果和图表。

## 当前结果解释

当前机器学习指标保存在 `outputs/metrics/china_all_ml_metrics.csv`。主要现象如下：

- 每日新增确诊：`GradientBoosting` 的测试集 R2 约为 0.623，说明滞后项和滑动统计特征能够捕捉一部分短期趋势。
- 每日新增死亡：R2 略低于 0，主要受 2023 年 1 月死亡数据补报峰值影响，模型难以仅凭历史滞后项提前预测这种统计口径修正。
- 每日新增治愈：R2 略低于 0，原因之一是 JHU recovered 数据在 2021-08-05 后不再可靠更新，可用样本较短且后期缺失。

报告中应如实保留负 R2，不为了美化结果而删除异常数据或伪造预测效果。

