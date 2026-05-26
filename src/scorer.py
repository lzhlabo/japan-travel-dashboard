"""
src/scorer.py
=============
綜合旅遊指數（TCI）計算模組。

提供公開函式：
    calculate_fare_score(fare_result)                          → pd.Series
    calculate_exchange_rate_score(rate_result)                 → pd.Series
    calculate_comfort_score_for_city(comfort_result, city)     → pd.Series
    calculate_tci_for_city(fare_result, rate_result,
                           comfort_result, city)               → ScoreResult
    calculate_tci_all_cities(fare_result, rate_result,
                             comfort_result)                   → dict[str, ScoreResult]

評分規則
--------
票價分數   : 票價越低 → 分數越高（反向正規化）
匯率分數   : JPY/TWD 匯率越低 → 分數越高（台幣可換更多日圓，換匯越划算）
舒適度分數 : 依各城市自己的氣溫、降雨、人潮計算（非全日本平均）

TCI 權重
--------
    TCI = fare_score    × 0.40
        + comfort_score × 0.50
        + rate_score    × 0.10

NaN 處理
--------
- 票價分數為 NaN 的月份，TCI 也為 NaN（資料不足，無法評分）
- 匯率分數為 NaN 時，TCI 仍可計算（以 0 代入加權）
- 舒適度分數為 NaN 時，TCI 仍可計算（以 0 代入加權）
"""

from __future__ import annotations

import pandas as pd

from .models import (
    ComfortAnalysisResult,
    FareAnalysisResult,
    RateAnalysisResult,
    ScoreResult,
)

# 完整月份索引
_ALL_MONTHS = pd.Index(range(1, 13), name="month")

# TCI 權重
_FARE_WEIGHT: float = 0.40
_RATE_WEIGHT: float = 0.10
_COMFORT_WEIGHT: float = 0.50


# ---------------------------------------------------------------------------
# 內部輔助：min-max 正規化
# ---------------------------------------------------------------------------

def _normalize(
    series: pd.Series,
    invert: bool = False,
    zero_denominator_default: float = 50.0,
) -> pd.Series:
    """
    對 Series 執行 min-max 正規化，回傳 0–100 分數。

    Parameters
    ----------
    series : pd.Series
        待正規化的數值序列（可含 NaN）。
    invert : bool
        True  → 值越小分數越高（用於票價、匯率：越低越好）
        False → 值越大分數越高（正向指標）
    zero_denominator_default : float
        當所有有效值相同（分母為 0）時，所有月份設為此值（預設 50.0）。

    Returns
    -------
    pd.Series
        正規化後的分數序列，值域 [0, 100]，NaN 月份保留 NaN。
    """
    valid = series.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)

    min_val = float(valid.min())
    max_val = float(valid.max())
    denominator = max_val - min_val

    if denominator == 0:
        result = series.copy().astype(float)
        result[result.notna()] = zero_denominator_default
        return result

    if invert:
        scores = 100.0 * (max_val - series) / denominator
    else:
        scores = 100.0 * (series - min_val) / denominator

    return scores.clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# 氣溫 / 人潮 子分數輔助函式
# ---------------------------------------------------------------------------

def _temperature_score(avg_temp_c: float) -> float:
    """
    將平均氣溫換算為 0–100 的舒適度分數。

    使用非對稱 Gaussian 曲線，讓偏離理想溫度時快速降分：

        理想區間 18–22°C → 100 分（最舒適）
        低溫側（< 18°C）：sigma_cold = 10，衰減較緩（台灣旅客對低溫有一定接受度）
        高溫側（> 22°C）：sigma_hot  =  7，衰減較快（高溫不舒適感更強烈）

    公式：
        temp in [18, 22]  → 100
        temp < 18         → 100 × exp(-((temp - 18)² / (2 × 10²)))
        temp > 22         → 100 × exp(-((temp - 22)² / (2 ×  7²)))

    代表性分數（供參考）：
        -5°C → ~16    0°C → ~27    5°C → ~42    10°C → ~61
        15°C → ~88   18°C → 100   20°C → 100   22°C → 100
        25°C → ~91   28°C → ~66   30°C → ~55   33°C → ~37

    設計原則：
        - 春秋（15–25°C）高分，盛夏（28°C+）與寒冬（5°C 以下）明顯下降
        - 不使用城市 hard code，所有城市共用同一公式
        - 結果 clip 至 [0, 100]
    """
    import math
    _IDEAL_LO:   float = 18.0
    _IDEAL_HI:   float = 22.0
    _SIGMA_COLD: float = 10.0   # 低溫側衰減寬度（較寬容）
    _SIGMA_HOT:  float = 7.0    # 高溫側衰減寬度（較嚴格）

    if _IDEAL_LO <= avg_temp_c <= _IDEAL_HI:
        score = 100.0
    elif avg_temp_c < _IDEAL_LO:
        score = 100.0 * math.exp(
            -((avg_temp_c - _IDEAL_LO) ** 2) / (2.0 * _SIGMA_COLD ** 2)
        )
    else:
        score = 100.0 * math.exp(
            -((avg_temp_c - _IDEAL_HI) ** 2) / (2.0 * _SIGMA_HOT ** 2)
        )
    return max(0.0, min(100.0, score))


def _crowd_score(avg_crowd: float) -> float:
    """
    將人潮指數（crowd_index）換算為 0–100 的舒適度子分數（非線性懲罰）。

    重要：crowd_index 是「人潮擁擠程度」，不是舒適分數。
        crowd_index = 1  → 人少、最舒適
        crowd_index = 10 → 非常擁擠、最不舒適

    此函式將擁擠程度轉換為舒適度子分數（crowd_score）：
    人潮越高 → crowd_score 越低。

    crowd_index 範圍 1–10，分三段：
        1–5：輕微扣分（二次曲線）  crowd=1→100, crowd=5→68
        5–7：中度扣分（線性）      crowd=5→68,  crowd=7→40
        7–10：重度扣分（二次曲線） crowd=7→40,  crowd=10→0（clip）

    注意：crowd=9 時公式結果為 40-(9-7)²×13.3 = -13.2，clip 至 0。
          crowd=10 時公式結果為 40-(10-7)²×13.3 = -79.7，clip 至 0。
    """
    if avg_crowd <= 5.0:
        score = 100.0 - (avg_crowd - 1.0) ** 2 * 2.0
    elif avg_crowd <= 7.0:
        score = 68.0 - (avg_crowd - 5.0) * 14.0
    else:
        score = 40.0 - (avg_crowd - 7.0) ** 2 * 13.3
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# 公開評分函式
# ---------------------------------------------------------------------------

def calculate_fare_score(fare_result: FareAnalysisResult) -> pd.Series:
    """
    計算各月份的票價分數（0–100）。

    票價越低 → 分數越高（反向正規化）。
    使用 monthly_min_fare（各月所有航空公司最低票價）作為基準。
    """
    scores = _normalize(fare_result.monthly_min_fare, invert=True)
    scores.name = "fare_score"
    return scores


def calculate_exchange_rate_score(rate_result: RateAnalysisResult) -> pd.Series:
    """
    計算各月份的匯率分數（0–100）。

    JPY/TWD 匯率越低（台幣可換更多日圓）→ 分數越高（反向正規化）。
    """
    scores = _normalize(rate_result.monthly_avg_rate, invert=True)
    scores.name = "exchange_rate_score"
    return scores


def calculate_comfort_subscores_for_city(
    comfort_result: ComfortAnalysisResult,
    city: str,
) -> "tuple[pd.Series, pd.Series, pd.Series]":
    """
    計算指定城市各月份的三個舒適度子分數（氣溫、降雨、人潮），供前端權重調整使用。

    Returns
    -------
    (temp_scores, rain_scores, crowd_scores) : tuple of pd.Series
        各 Series 的 index=month(1–12)，值為 0–100 分數。
    """
    _nan_series = pd.Series(index=_ALL_MONTHS, dtype=float)

    if comfort_result.monthly_comfort.empty:
        return _nan_series.copy(), _nan_series.copy(), _nan_series.copy()

    df = comfort_result.monthly_comfort.reset_index()
    city_df = df[df["city"] == city]
    if city_df.empty:
        return _nan_series.copy(), _nan_series.copy(), _nan_series.copy()

    monthly = city_df.groupby("month").agg(
        avg_temp=("avg_temp_c", "mean"),
        avg_rain=("rain_probability_pct", "mean"),
        avg_crowd=("crowd_index", "mean"),
    ).reindex(_ALL_MONTHS)

    temp_scores = monthly["avg_temp"].apply(
        lambda v: _temperature_score(float(v)) if not pd.isna(v) else float("nan")
    )
    rain_scores = (100.0 - monthly["avg_rain"]).clip(0.0, 100.0)
    crowd_scores = monthly["avg_crowd"].apply(
        lambda v: _crowd_score(float(v)) if not pd.isna(v) else float("nan")
    )

    temp_scores.name = "temp_score"
    rain_scores.name = "rain_score"
    crowd_scores.name = "crowd_score"

    return temp_scores, rain_scores, crowd_scores


def calculate_comfort_score_for_city(
    comfort_result: ComfortAnalysisResult,
    city: str,
) -> pd.Series:
    """
    計算指定城市各月份的舒適度分數（0–100）。

    使用該城市自己的氣溫、降雨機率、人潮指數，不與其他城市平均。

    Parameters
    ----------
    comfort_result : ComfortAnalysisResult
        由 analyze_comfort() 產生的舒適度分析結果。
    city : str
        目的地城市名稱（例：「東京」）。

    Returns
    -------
    pd.Series
        index=month(1–12)，值為舒適度分數（float, 0–100）。
        若該城市無資料，回傳全 NaN。

    Notes
    -----
    三個子分數（使用該城市該月份的數值）：

    temperature_score（氣溫分數，非線性懲罰）：
        10–25°C = 100（最舒適）
        低溫：0–10°C 每降 1°C 扣 2 分；0°C 以下每降 1°C 扣 3 分
        高溫：25–30°C 每升 1°C 扣 3 分；30°C 以上每升 1°C 扣 5 分

    rain_score（降雨分數）：
        rain_score = 100 − rain_probability_pct，clip [0, 100]

    crowd_score（人潮分數，非線性懲罰）：
        crowd 1–5：100 − (crowd−1)² × 2.0（輕微扣分）
        crowd 5–7：68 − (crowd−5) × 14.0（中度扣分）
        crowd 7–10：40 − (crowd−7)² × 13.3（重度扣分）

    最終公式：
        comfort_score = temperature_score × 0.4
                      + rain_score        × 0.3
                      + crowd_score       × 0.3
    """
    if comfort_result.monthly_comfort.empty:
        return pd.Series(index=_ALL_MONTHS, dtype=float, name="comfort_score")

    df = comfort_result.monthly_comfort.reset_index()

    # 只取指定城市的資料
    city_df = df[df["city"] == city]
    if city_df.empty:
        return pd.Series(index=_ALL_MONTHS, dtype=float, name="comfort_score")

    # 依月份聚合（同城市可能有多筆記錄時取平均）
    monthly = city_df.groupby("month").agg(
        avg_temp=("avg_temp_c", "mean"),
        avg_rain=("rain_probability_pct", "mean"),
        avg_crowd=("crowd_index", "mean"),
    ).reindex(_ALL_MONTHS)

    # 三個子分數
    temp_scores = monthly["avg_temp"].apply(
        lambda v: _temperature_score(float(v)) if not pd.isna(v) else float("nan")
    )
    rain_scores = (100.0 - monthly["avg_rain"]).clip(0.0, 100.0)
    crowd_scores = monthly["avg_crowd"].apply(
        lambda v: _crowd_score(float(v)) if not pd.isna(v) else float("nan")
    )

    scores = (
        temp_scores  * 0.4
        + rain_scores  * 0.3
        + crowd_scores * 0.3
    )
    scores = scores.clip(0.0, 100.0)
    scores.name = "comfort_score"
    return scores


def calculate_tci_for_city(
    fare_result: FareAnalysisResult,
    rate_result: RateAnalysisResult,
    comfort_result: ComfortAnalysisResult,
    city: str,
    fare_estimated: "pd.Series | None" = None,
) -> ScoreResult:
    """
    計算指定城市的綜合旅遊指數（TCI）。

    fare_result 應已依該城市過濾（只含飛往該城市的票價，可含估算補值）。
    匯率資料共用，舒適度依城市個別計算。

    Parameters
    ----------
    fare_result : FareAnalysisResult
        已依目的地城市過濾的票價分析結果（可由 analyze_fares_for_city_with_fallback() 產生）。
    rate_result : RateAnalysisResult
    comfort_result : ComfortAnalysisResult
    city : str
        目的地城市名稱。
    fare_estimated : pd.Series | None
        index=month(1–12)，True 表示該月票價為估算值。若為 None，全設為 False。

    Returns
    -------
    ScoreResult
    """
    fare_score = calculate_fare_score(fare_result).reindex(_ALL_MONTHS)
    rate_score = calculate_exchange_rate_score(rate_result).reindex(_ALL_MONTHS)
    comfort_score = calculate_comfort_score_for_city(
        comfort_result, city
    ).reindex(_ALL_MONTHS)

    # 取得三個舒適度子分數，供前端權重調整使用
    temp_score, rain_score, crowd_score = calculate_comfort_subscores_for_city(
        comfort_result, city
    )
    temp_score = temp_score.reindex(_ALL_MONTHS)
    rain_score = rain_score.reindex(_ALL_MONTHS)
    crowd_score = crowd_score.reindex(_ALL_MONTHS)

    has_any_data = rate_score.notna() | comfort_score.notna() | fare_score.notna()

    tci = (
        fare_score.fillna(0.0) * _FARE_WEIGHT
        + rate_score.fillna(0.0) * _RATE_WEIGHT
        + comfort_score.fillna(0.0) * _COMFORT_WEIGHT
    )
    tci[~has_any_data] = float("nan")

    total_score = tci.clip(0.0, 100.0).round(1)
    total_score.name = "tci"

    # 建立 fare_estimated Series
    if fare_estimated is None:
        est = pd.Series(False, index=_ALL_MONTHS, dtype=bool)
    else:
        est = fare_estimated.reindex(_ALL_MONTHS).fillna(False).astype(bool)

    return ScoreResult(
        fare_score=fare_score,
        rate_score=rate_score,
        comfort_score=comfort_score,
        total_score=total_score,
        fare_estimated=est,
        temp_score=temp_score,
        rain_score=rain_score,
        crowd_score=crowd_score,
    )


def calculate_tci_all_cities(
    fare_records: "list",
    rate_result: RateAnalysisResult,
    comfort_result: ComfortAnalysisResult,
) -> "dict[str, ScoreResult]":
    """
    計算所有城市的 TCI，回傳 {city: ScoreResult} 字典。

    每個城市使用自己的票價（依 destination 過濾，缺失月份以跨城市平均估算補值）、
    自己的舒適度，共用匯率。

    Parameters
    ----------
    fare_records : list[FareRecord]
        原始票價記錄清單（未過濾），由 load_fares() 回傳。
    rate_result : RateAnalysisResult
    comfort_result : ComfortAnalysisResult

    Returns
    -------
    dict[str, ScoreResult]
        key: 城市名稱，value: 該城市的 ScoreResult（含 fare_estimated 標記）
    """
    from .analyzer import analyze_fares_for_city_with_fallback

    if comfort_result.monthly_comfort.empty:
        return {}

    cities = comfort_result.monthly_comfort.index.get_level_values("city").unique().tolist()

    results: dict[str, ScoreResult] = {}
    for city in cities:
        city_fare_result, fare_estimated = analyze_fares_for_city_with_fallback(
            fare_records, city
        )
        results[city] = calculate_tci_for_city(
            city_fare_result, rate_result, comfort_result, city,
            fare_estimated=fare_estimated,
        )
    return results


# ---------------------------------------------------------------------------
# 向後相容：全城市平均模式（供舊測試使用）
# ---------------------------------------------------------------------------

def calculate_comfort_score(comfort_result: ComfortAnalysisResult) -> pd.Series:
    """
    計算各月份的舒適度分數（全城市平均模式，向後相容）。

    將所有城市的資料平均後計算，等同舊版行為。
    新程式碼請改用 calculate_comfort_score_for_city()。
    """
    if comfort_result.monthly_comfort.empty:
        return pd.Series(index=_ALL_MONTHS, dtype=float, name="comfort_score")

    df = comfort_result.monthly_comfort.reset_index()
    monthly_avg = df.groupby("month").agg(
        avg_temp=("avg_temp_c", "mean"),
        avg_rain=("rain_probability_pct", "mean"),
        avg_crowd=("crowd_index", "mean"),
    )
    temp_scores = monthly_avg["avg_temp"].apply(
        lambda v: _temperature_score(float(v)) if not pd.isna(v) else float("nan")
    )
    rain_scores = (100.0 - monthly_avg["avg_rain"]).clip(0.0, 100.0)
    crowd_scores = monthly_avg["avg_crowd"].apply(
        lambda v: _crowd_score(float(v)) if not pd.isna(v) else float("nan")
    )
    scores = (temp_scores * 0.4 + rain_scores * 0.3 + crowd_scores * 0.3)
    scores = scores.clip(0.0, 100.0).reindex(_ALL_MONTHS)
    scores.name = "comfort_score"
    return scores


def calculate_tci(
    fare_result: FareAnalysisResult,
    rate_result: RateAnalysisResult,
    comfort_result: ComfortAnalysisResult,
) -> ScoreResult:
    """
    計算綜合旅遊指數（全城市平均模式，向後相容）。

    新程式碼請改用 calculate_tci_for_city() 或 calculate_tci_all_cities()。
    """
    fare_score = calculate_fare_score(fare_result).reindex(_ALL_MONTHS)
    rate_score = calculate_exchange_rate_score(rate_result).reindex(_ALL_MONTHS)
    comfort_score = calculate_comfort_score(comfort_result).reindex(_ALL_MONTHS)

    tci = (
        fare_score * _FARE_WEIGHT
        + rate_score.fillna(0.0) * _RATE_WEIGHT
        + comfort_score.fillna(0.0) * _COMFORT_WEIGHT
    )
    total_score = tci.clip(0.0, 100.0).round(1)
    total_score.name = "tci"

    return ScoreResult(
        fare_score=fare_score,
        rate_score=rate_score,
        comfort_score=comfort_score,
        total_score=total_score,
    )
