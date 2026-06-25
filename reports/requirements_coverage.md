# 大作业要求与模型覆盖矩阵

## 从课程文件提取的核心要求

课程题目一要求围绕“疫情传播模型与预测模型方法”完成以下内容：

- 理解疫情传播规律与数据特征；
- 掌握时间序列预测与回归模型的建模流程；
- 使用实际疫情数据进行建模与评估；
- 结合编程实现疫情传播预测模型及可视化分析。

模型类型至少覆盖两类：

- 传统模型：SIR、SEIR、扩展 SEIRS/SEIQR 或其他时间序列模型；
- 机器学习/深度学习模型：线性回归、决策树、XGBoost、Random Forest、LSTM、GRU 或 Transformer 等。

建模必须解决的问题：

- 每日新增确诊、治愈、死亡人数；
- 区域传播趋势；
- 未来 7 天、14 天趋势预测；
- 可视化分析与结果评估，包括时间趋势图、模型误差对比图等；
- 评价指标包括 RMSE、MAE、R2。

PPT 中传统传染病模型的关键数据构造为：

- `i(t)`：现存感染者，可由累计确诊减去累计治愈和累计死亡得到；
- `r(t)`：移除者，可由累计治愈加累计死亡得到；
- SIR 类模型主要拟合 `i(t)` 和 `r(t)` 的传播过程。

## 本项目应覆盖的数据对象

| 数据对象 | 字段或构造方式 | 用途 |
| --- | --- | --- |
| 累计确诊 | `cumulative_confirmed` | 趋势分析、SIR 类模型舱室构造、累计预测对比 |
| 累计死亡 | `cumulative_deaths` | 趋势分析、移除者构造、死亡新增预测来源 |
| 累计治愈 | `cumulative_recovered` | 趋势分析、移除者构造、治愈新增预测来源 |
| 每日新增确诊 | `daily_confirmed` | 课程明确要求的每日新增预测目标 |
| 每日新增死亡 | `daily_deaths` | 课程明确要求的每日新增预测目标 |
| 每日新增治愈 | `daily_recovered` | 课程明确要求的每日新增预测目标 |
| 现存感染者 | `infected = confirmed - deaths - recovered` | SIR 类模型主要拟合对象 |
| 移除者 | `removed = deaths + recovered` | SIR 类模型主要拟合对象 |
| 区域数据 | 全国聚合 + 省份/地区面板 | 区域传播趋势分析 |

## 三类模型的拟合与预测口径

| 模型 | 拟合数据 | 预测数据 | 为什么这样设定 |
| --- | --- | --- | --- |
| 固定参数 SIR | 早期可靠 recovered 数据窗口中的 `infected`、`removed`、`confirmed` | 未来 7/14 天的 `infected`、`removed`、`confirmed`，并派生 `daily_confirmed`、`daily_removed` | SIR 的变量定义就是易感者、感染者、移除者，不能天然拆分每日死亡和每日治愈 |
| 时变参数 SIR | 同一窗口中的 `infected`、`removed`、`confirmed`，并由差分估计 `beta(t)`、`gamma(t)` | 未来 7/14 天的 `infected`、`removed`、`confirmed`，并派生 `daily_confirmed`、`daily_removed` | 比固定参数 SIR 更贴合 PPT，可解释接触率降低、移除率变化对传播趋势的影响 |
| GradientBoosting | 按时间顺序构造滞后特征，分别训练 `daily_confirmed`、`daily_deaths`、`daily_recovered` | 未来 7/14 天每日新增确诊、死亡、治愈 | 机器学习模型负责覆盖课程明确要求的三类每日新增预测 |

## 为避免缺失，后续报告应采用的结果结构

1. 数据趋势分析：累计确诊、累计死亡、累计治愈；每日新增确诊、死亡、治愈。
2. 区域传播趋势：使用省份/地区面板展示不同地区传播差异。
3. 传统模型主线：固定参数 SIR 与时变参数 SIR 均拟合 `infected`、`removed`、`confirmed`。
4. 机器学习预测：GradientBoosting 分别预测 `daily_confirmed`、`daily_deaths`、`daily_recovered`。
5. 公平补充实验：可让 GradientBoosting 在与 SIR 类模型相同窗口上拟合 `infected`、`removed`、`confirmed`，用于说明机器学习模型在平滑累计舱室数据上表现会更高，但不代表其具备传播机制解释能力。
6. 未来预测：所有模型都输出 7 天和 14 天趋势，SIR 模型输出舱室趋势，GradientBoosting 输出每日新增趋势。
7. 指标表：分别给出传统模型舱室拟合指标、机器学习每日新增预测指标，不混淆评价对象。

## 当前项目需要注意的缺口

- 已有固定参数 SIR、时变参数 SIR、GradientBoosting 三个模型；
- 已有每日新增确诊、死亡、治愈的机器学习预测；
- 已有固定参数 SIR/时变参数 SIR 对 `infected`、`removed`、`confirmed` 的传统模型拟合；
- 还应在报告中明确说明：SIR 类模型不直接预测每日死亡和每日治愈，而是预测合并后的 `removed`；
- 还应补充区域传播趋势图，避免只在全国聚合数据上展示；
- 如果要公平比较三种模型，应增加 GradientBoosting 对 `infected`、`removed`、`confirmed` 的同窗口拟合实验。
