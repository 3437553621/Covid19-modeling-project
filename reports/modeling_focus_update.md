# Modeling Focus Update

## 新的建模重心

本项目后续论文和结果展示以传统传染病动力学模型为主，机器学习模型作为辅助预测对照。当前主线调整为：

1. 固定参数 SIR 模型：作为基础传统模型，解释易感者、感染者、移除者之间的转化关系。
2. 时变参数 SIR 模型：作为新增传统模型，用每日差分估计 `beta(t)` 和 `gamma(t)`，解释防控措施、接触率变化和医疗救治变化对传播过程的影响。
3. GradientBoosting 模型：作为唯一保留的机器学习预测模型，用滞后特征和滑动统计特征预测每日新增确诊、死亡和治愈。

## 时变参数 SIR 模型说明

时变参数 SIR 沿用 SIR 的三个舱室：

- `S`：易感者；
- `I`：感染者；
- `R`：移除者，近似表示治愈人数与死亡人数之和。

模型参数含义如下：

- `beta(t)`：第 `t` 天的经验感染率，由新增感染量与感染者数量的比值近似估计；
- `gamma(t)`：第 `t` 天的移除率，由新增移除者与感染者数量的比值近似估计；
- `R0(t) = beta(t) / gamma(t)`：随时间变化的传播强度近似指标。

当前时变参数 SIR 拟合结果保存在：

- `outputs/metrics/china_all_time_varying_sir_parameters.csv`
- `outputs/metrics/china_all_time_varying_sir_daily_parameters.csv`
- `outputs/metrics/china_all_time_varying_sir_metrics.csv`
- `outputs/predictions/china_all_time_varying_sir_fit.csv`
- `outputs/figures/china_all_time_varying_sir_fit.png`

## 当前模型对比结论

从 `outputs/metrics/metrics.csv` 可以看到，固定参数 SIR 用一组固定 `beta`、`gamma` 概括早期传播过程，适合解释基础机制；时变参数 SIR 通过每日差分反推 `beta(t)` 和 `gamma(t)`，更适合展示传播强度随防控和救治变化而改变。时变参数 SIR 的拟合指标很高，是因为参数直接来自同一段观测数据差分，报告中应将其解释为机制分析和参数变化分析，而不是普通机器学习意义上的独立测试集预测。

因此报告中建议采用如下叙述：

传统模型用于解释疫情传播机制和参数意义；机器学习模型用于测试短期时间序列预测能力。二者不是简单替代关系，而是分别回答“传播机制如何形成”和“短期新增人数能否预测”两个问题。
