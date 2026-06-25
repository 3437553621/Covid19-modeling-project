from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


LAGS = list(range(1, 15)) + [21, 28]
ROLLING_WINDOWS = [3, 7, 14, 28]
FEATURE_COLUMNS = [
    "day_index",
    "day_of_week",
    "is_weekend",
    "month",
    "week_of_year",
    "dow_sin",
    "dow_cos",
    *[f"lag_{lag}" for lag in LAGS],
    *[f"rolling_mean_{window}" for window in ROLLING_WINDOWS],
    *[f"rolling_median_{window}" for window in ROLLING_WINDOWS],
    *[f"rolling_std_{window}" for window in ROLLING_WINDOWS],
    *[f"rolling_max_{window}" for window in ROLLING_WINDOWS],
    "ewm_7",
    "ewm_14",
    "diff_1",
    "diff_7",
    "ratio_to_mean_7",
]


@dataclass
class TrainTestSplit:
    train: pd.DataFrame
    test: pd.DataFrame
    feature_columns: list[str]


class FeatureColumnRegressor:
    """A deterministic baseline that predicts from one leakage-free feature column."""

    def __init__(self, feature_name: str):
        self.feature_name = feature_name

    def fit(self, _x: pd.DataFrame, _y: pd.Series) -> "FeatureColumnRegressor":
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return x[self.feature_name].to_numpy(dtype=float)


def build_lag_features(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Build supervised time-series features without future leakage."""
    required = {"date", target_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    data = df[["date", target_col]].copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date").dropna(subset=[target_col]).reset_index(drop=True)
    data["target"] = data[target_col].astype(float)
    data["day_index"] = np.arange(len(data), dtype=float)
    data["day_of_week"] = data["date"].dt.dayofweek.astype(float)
    data["is_weekend"] = data["day_of_week"].isin([5, 6]).astype(float)
    data["month"] = data["date"].dt.month.astype(float)
    data["week_of_year"] = data["date"].dt.isocalendar().week.astype(float)
    data["dow_sin"] = np.sin(2 * np.pi * data["day_of_week"] / 7)
    data["dow_cos"] = np.cos(2 * np.pi * data["day_of_week"] / 7)

    for lag in LAGS:
        data[f"lag_{lag}"] = data["target"].shift(lag)

    shifted = data["target"].shift(1)
    for window in ROLLING_WINDOWS:
        min_periods = max(2, window // 2)
        rolling = shifted.rolling(window=window, min_periods=min_periods)
        data[f"rolling_mean_{window}"] = rolling.mean()
        data[f"rolling_median_{window}"] = rolling.median()
        data[f"rolling_std_{window}"] = rolling.std().fillna(0)
        data[f"rolling_max_{window}"] = rolling.max()

    data["ewm_7"] = shifted.ewm(span=7, adjust=False).mean()
    data["ewm_14"] = shifted.ewm(span=14, adjust=False).mean()
    data["diff_1"] = data["lag_1"] - data["lag_2"]
    data["diff_7"] = data["lag_1"] - data["lag_7"]
    data["ratio_to_mean_7"] = data["lag_1"] / (data["rolling_mean_7"] + 1)
    return data.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)


def split_train_test(feature_df: pd.DataFrame, test_ratio: float = 0.2) -> TrainTestSplit:
    if not 0 < test_ratio < 0.8:
        raise ValueError("test_ratio must be between 0 and 0.8.")
    if len(feature_df) < 30:
        raise ValueError("Need at least 30 feature rows for train/test split.")

    split_idx = int(len(feature_df) * (1 - test_ratio))
    split_idx = min(max(split_idx, 14), len(feature_df) - 7)
    train = feature_df.iloc[:split_idx].copy()
    test = feature_df.iloc[split_idx:].copy()
    return TrainTestSplit(train=train, test=test, feature_columns=FEATURE_COLUMNS)


def make_models(random_state: int = 42) -> dict[str, object]:
    return {
        "NaivePersistence": FeatureColumnRegressor("lag_1"),
        "RollingMean7": FeatureColumnRegressor("rolling_mean_7"),
        "LinearRegression": LinearRegression(),
        "RidgeRegression": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "RandomForest": RandomForestRegressor(
            n_estimators=500,
            max_depth=10,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=1,
        ),
        "ExtraTrees": ExtraTreesRegressor(
            n_estimators=500,
            max_depth=None,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=1,
        ),
        "GradientBoosting": GradientBoostingRegressor(
            n_estimators=500,
            learning_rate=0.03,
            max_depth=2,
            subsample=0.9,
            loss="absolute_error",
            random_state=random_state,
        ),
    }


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    true = np.asarray(y_true, dtype=float)
    pred = np.maximum(np.asarray(y_pred, dtype=float), 0)
    mask = np.isfinite(true) & np.isfinite(pred)
    true = true[mask]
    pred = pred[mask]
    if len(true) == 0:
        return {"RMSE": np.nan, "MAE": np.nan, "R2": np.nan}

    rmse = float(np.sqrt(np.mean((true - pred) ** 2)))
    mae = float(np.mean(np.abs(true - pred)))
    denom = float(np.sum((true - np.mean(true)) ** 2))
    r2 = float(1 - np.sum((true - pred) ** 2) / denom) if denom > 0 else np.nan
    return {"RMSE": rmse, "MAE": mae, "R2": r2}


def train_and_predict(
    feature_df: pd.DataFrame,
    test_ratio: float = 0.2,
    random_state: int = 42,
    model_names: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    split = split_train_test(feature_df, test_ratio=test_ratio)
    x_train = split.train[split.feature_columns]
    y_train = split.train["target"]
    x_test = split.test[split.feature_columns]
    y_test = split.test["target"]

    metrics_rows = []
    prediction_frames = []
    fitted_models: dict[str, object] = {}

    candidate_models = make_models(random_state=random_state)
    if model_names is not None:
        missing_models = set(model_names) - set(candidate_models)
        if missing_models:
            raise ValueError(f"Unknown model names: {sorted(missing_models)}")
        candidate_models = {name: candidate_models[name] for name in model_names}

    for model_name, model in candidate_models.items():
        model.fit(x_train, y_train)
        pred = np.maximum(model.predict(x_test), 0)
        fitted_models[model_name] = model

        row = {
            "model": model_name,
            "train_start_date": split.train["date"].min().date().isoformat(),
            "train_end_date": split.train["date"].max().date().isoformat(),
            "test_start_date": split.test["date"].min().date().isoformat(),
            "test_end_date": split.test["date"].max().date().isoformat(),
        }
        row.update(evaluate_predictions(y_test.to_numpy(), pred))
        metrics_rows.append(row)

        frame = split.test[["date", "target"]].copy()
        frame = frame.rename(columns={"target": "actual"})
        frame["model"] = model_name
        frame["prediction"] = pred
        frame["split"] = "test"
        prediction_frames.append(frame)

    return pd.DataFrame(metrics_rows), pd.concat(prediction_frames, ignore_index=True), fitted_models


def _features_for_next(history: list[float], next_date: pd.Timestamp) -> dict[str, float]:
    idx = float(len(history))
    values = pd.Series(history, dtype=float)
    features = {
        "day_index": idx,
        "day_of_week": float(next_date.dayofweek),
        "is_weekend": float(next_date.dayofweek in [5, 6]),
        "month": float(next_date.month),
        "week_of_year": float(next_date.isocalendar().week),
        "dow_sin": float(np.sin(2 * np.pi * next_date.dayofweek / 7)),
        "dow_cos": float(np.cos(2 * np.pi * next_date.dayofweek / 7)),
    }

    for lag in LAGS:
        features[f"lag_{lag}"] = float(history[-lag]) if len(history) >= lag else float(history[-1])

    for window in ROLLING_WINDOWS:
        last_values = values.iloc[-window:]
        features[f"rolling_mean_{window}"] = float(last_values.mean())
        features[f"rolling_median_{window}"] = float(last_values.median())
        features[f"rolling_std_{window}"] = float(last_values.std(ddof=1)) if len(last_values) > 1 else 0.0
        features[f"rolling_max_{window}"] = float(last_values.max())

    features["ewm_7"] = float(values.ewm(span=7, adjust=False).mean().iloc[-1])
    features["ewm_14"] = float(values.ewm(span=14, adjust=False).mean().iloc[-1])
    features["diff_1"] = features["lag_1"] - features["lag_2"]
    features["diff_7"] = features["lag_1"] - features["lag_7"]
    features["ratio_to_mean_7"] = features["lag_1"] / (features["rolling_mean_7"] + 1)
    return features


def recursive_forecast(model: object, history_df: pd.DataFrame, target_col: str, forecast_days: int = 14) -> pd.DataFrame:
    if forecast_days <= 0:
        raise ValueError("forecast_days must be positive.")

    history = history_df.sort_values("date").dropna(subset=[target_col]).copy()
    history["date"] = pd.to_datetime(history["date"])
    values = history[target_col].astype(float).tolist()
    if len(values) < max(LAGS):
        raise ValueError(f"Need at least {max(LAGS)} observations for recursive forecasting.")

    last_date = history["date"].max()
    rows = []
    for step in range(1, forecast_days + 1):
        next_date = last_date + pd.Timedelta(days=step)
        feature_row = _features_for_next(values, next_date)
        x_next = pd.DataFrame([feature_row])[FEATURE_COLUMNS]
        pred = float(np.maximum(model.predict(x_next)[0], 0))
        values.append(pred)
        rows.append({"date": next_date, "forecast_day": step, "prediction": pred})
    return pd.DataFrame(rows)
