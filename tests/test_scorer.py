"""
tests/test_scorer.py
====================
Scorer 單元測試。

涵蓋：
  - calculate_fare_score()
      正向/反向正規化、分母為零、NaN 傳播、值域 [0,100]
  - calculate_exchange_rate_score()
      正向正規化、分母為零、NaN 傳播
  - calculate_comfort_score()
      公式正確性、值域 clip、空輸入、NaN 月份
  - calculate_tci()
      加權計算、NaN 傳播規則、最佳月份識別、值域 [0,100]
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.analyzer import analyze_comfort, analyze_exchange_rates, analyze_fares
from src.models import (
    ComfortAnalysisResult,
    ComfortScoreRecord,
    ExchangeRateRecord,
    FareAnalysisResult,
    FareRecord,
    RateAnalysisResult,
)
from src.scorer import (
    calculate_comfort_score,
    calculate_exchange_rate_score,
    calculate_fare_score,
    calculate_tci,
    calculate_comfort_score_for_city,
    calculate_tci_for_city,
    calculate_tci_all_cities,
)

_ALL_MONTHS = list(range(1, 13))


# ---------------------------------------------------------------------------
# 輔助工廠函式
# ---------------------------------------------------------------------------

def _make_fare_result(monthly_min: dict[int, float]) -> FareAnalysisResult:
    """建立只含 monthly_min_fare 的 FareAnalysisResult（avg_by_airline 留空）。"""
    s = pd.Series(monthly_min, name="min_fare").reindex(range(1, 13))
    s.index.name = "month"
    return FareAnalysisResult(
        monthly_avg_by_airline=pd.DataFrame(index=s.index, columns=["CI", "BR", "JX"], dtype=float),
        monthly_min_fare=s,
    )


def _make_rate_result(monthly_avg: dict[int, float]) -> RateAnalysisResult:
    """建立只含 monthly_avg_rate 的 RateAnalysisResult。"""
    s = pd.Series(monthly_avg, name="jpy_twd_rate").reindex(range(1, 13))
    s.index.name = "month"
    valid = s.dropna()
    annual = round(float(valid.mean()), 4) if not valid.empty else 0.0
    # 最佳換匯月份 = 匯率最低的月份（台幣可換最多日圓）
    best = sorted(int(m) for m in valid[valid == valid.min()].index) if not valid.empty else []
    return RateAnalysisResult(monthly_avg_rate=s, annual_avg_rate=annual, best_months=best)


def _make_comfort_result(data: list[tuple]) -> ComfortAnalysisResult:
    """
    data: list of (month, city, rain_pct, crowd_index)
    建立 ComfortAnalysisResult。
    """
    records = [
        ComfortScoreRecord(month, city, 20.0, rain, crowd)
        for month, city, rain, crowd in data
    ]
    return analyze_comfort(records)


# ===========================================================================
# calculate_fare_score
# ===========================================================================

class TestCalculateFareScore:

    def test_lowest_fare_gets_100(self) -> None:
        """最低票價月份應得 100 分。"""
        result = _make_fare_result({1: 10000, 6: 15000, 12: 20000})
        scores = calculate_fare_score(result)
        assert scores[1] == pytest.approx(100.0)

    def test_highest_fare_gets_0(self) -> None:
        """最高票價月份應得 0 分。"""
        result = _make_fare_result({1: 10000, 6: 15000, 12: 20000})
        scores = calculate_fare_score(result)
        assert scores[12] == pytest.approx(0.0)

    def test_middle_fare_gets_50(self) -> None:
        """中間票價應得 50 分（線性正規化）。"""
        result = _make_fare_result({1: 10000, 6: 15000, 12: 20000})
        scores = calculate_fare_score(result)
        assert scores[6] == pytest.approx(50.0)

    def test_all_same_fare_gets_50(self) -> None:
        """所有月份票價相同（分母為零）應全設為 50.0。"""
        result = _make_fare_result({m: 15000 for m in range(1, 13)})
        scores = calculate_fare_score(result)
        for m in range(1, 13):
            assert scores[m] == pytest.approx(50.0)

    def test_nan_month_stays_nan(self) -> None:
        """無票價資料的月份應保留 NaN。"""
        result = _make_fare_result({1: 10000, 12: 20000})
        scores = calculate_fare_score(result)
        for m in range(2, 12):
            assert pd.isna(scores[m])

    def test_scores_within_0_to_100(self) -> None:
        """所有有效分數應在 [0, 100] 範圍內。"""
        result = _make_fare_result({m: 10000 + m * 1000 for m in range(1, 13)})
        scores = calculate_fare_score(result)
        valid = scores.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_empty_fare_result_all_nan(self) -> None:
        """空票價資料應回傳全 NaN。"""
        result = _make_fare_result({})
        scores = calculate_fare_score(result)
        assert scores.isna().all()

    def test_index_covers_all_12_months(self) -> None:
        """結果 index 應涵蓋 1–12 月。"""
        result = _make_fare_result({1: 10000})
        scores = calculate_fare_score(result)
        assert list(scores.index) == _ALL_MONTHS


# ===========================================================================
# calculate_exchange_rate_score
# ===========================================================================

class TestCalculateExchangeRateScore:

    def test_lowest_rate_gets_100(self) -> None:
        """最低匯率月份應得 100 分（匯率低 = 台幣可換更多日圓）。"""
        result = _make_rate_result({1: 0.2078, 8: 0.2125, 12: 0.2085})
        scores = calculate_exchange_rate_score(result)
        assert scores[1] == pytest.approx(100.0)

    def test_highest_rate_gets_0(self) -> None:
        """最高匯率月份應得 0 分（匯率高 = 台幣換到較少日圓）。"""
        result = _make_rate_result({1: 0.2078, 8: 0.2125, 12: 0.2085})
        scores = calculate_exchange_rate_score(result)
        assert scores[8] == pytest.approx(0.0)

    def test_all_same_rate_gets_50(self) -> None:
        """所有月份匯率相同（分母為零）應全設為 50.0。"""
        result = _make_rate_result({m: 0.2100 for m in range(1, 13)})
        scores = calculate_exchange_rate_score(result)
        for m in range(1, 13):
            assert scores[m] == pytest.approx(50.0)

    def test_nan_month_stays_nan(self) -> None:
        """無匯率資料的月份應保留 NaN。"""
        result = _make_rate_result({1: 0.2100, 12: 0.2120})
        scores = calculate_exchange_rate_score(result)
        for m in range(2, 12):
            assert pd.isna(scores[m])

    def test_scores_within_0_to_100(self) -> None:
        """所有有效分數應在 [0, 100] 範圍內。"""
        result = _make_rate_result({m: 0.2078 + m * 0.0004 for m in range(1, 13)})
        scores = calculate_exchange_rate_score(result)
        valid = scores.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_linear_interpolation(self) -> None:
        """中間匯率應得到線性插值分數（反向：中間值得 50 分）。"""
        result = _make_rate_result({1: 0.2000, 6: 0.2050, 12: 0.2100})
        scores = calculate_exchange_rate_score(result)
        # 月份 1 最低匯率 → 100 分；月份 12 最高匯率 → 0 分；月份 6 中間 → 50 分
        assert scores[6] == pytest.approx(50.0, abs=0.1)


# ===========================================================================
# calculate_comfort_score
# ===========================================================================

class TestCalculateComfortScore:

    # --- temperature_score sub-tests ---

    def test_temp_in_ideal_range_gets_100(self) -> None:
        """氣溫在 18–22°C 理想區間，temperature_score 應為 100。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(1, "東京", 20.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # temp=100, rain=100, crowd=100 → comfort=100.0
        assert scores[1] == pytest.approx(100.0, abs=0.2)

    def test_temp_at_18_gets_100(self) -> None:
        """氣溫 18°C（理想區間下限），temperature_score 應為 100。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(6, "東京", 18.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[6] == pytest.approx(100.0, abs=0.2)

    def test_temp_at_22_gets_100(self) -> None:
        """氣溫 22°C（理想區間上限），temperature_score 應為 100。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(6, "東京", 22.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[6] == pytest.approx(100.0, abs=0.2)

    def test_temp_below_ideal_decreases_score(self) -> None:
        """氣溫低於 18°C 時，分數應隨溫度降低而下降（Gaussian 衰減）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=5°C → temp_score ≈ 42.96
        # comfort = 42.96*0.4 + 100*0.3 + 100*0.3 ≈ 77.2
        records = [ComfortScoreRecord(1, "東京", 5.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[1] == pytest.approx(77.2, abs=1.0)

    def test_temp_below_0_gets_very_low_score(self) -> None:
        """氣溫 -5°C，temperature_score 應明顯偏低（Gaussian 快速衰減）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=-5°C → temp_score ≈ 7.1
        # comfort = 7.1*0.4 + 100*0.3 + 100*0.3 ≈ 62.8
        records = [ComfortScoreRecord(1, "札幌", -5.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[1] == pytest.approx(62.8, abs=1.0)

    def test_temp_above_ideal_decreases_score(self) -> None:
        """氣溫高於 22°C 時，分數應隨溫度升高而下降（高溫側衰減更快）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=27°C → temp_score ≈ 77.5
        # comfort = 77.5*0.4 + 100*0.3 + 100*0.3 ≈ 91.0
        records = [ComfortScoreRecord(6, "東京", 27.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[6] == pytest.approx(91.0, abs=1.0)

    def test_temp_above_30_gets_low_score(self) -> None:
        """氣溫 32°C，temperature_score 應明顯偏低（高溫懲罰）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=32°C → temp_score ≈ 36.0
        # comfort = 36.0*0.4 + 100*0.3 + 100*0.3 ≈ 74.4
        records = [ComfortScoreRecord(7, "東京", 32.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert scores[7] == pytest.approx(74.4, abs=1.0)

    def test_temp_score_clipped_at_zero(self) -> None:
        """極低氣溫 temperature_score 應 clip 至 0。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=-40°C → temp_score ≈ 0 (Gaussian → 0)
        records = [ComfortScoreRecord(1, "札幌", -40.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # temp=0, rain=100, crowd=100 → 0*0.4+100*0.3+100*0.3 = 60.0
        assert scores[1] == pytest.approx(60.0, abs=0.5)

    def test_hot_temp_worse_than_cold_temp_at_same_distance(self) -> None:
        """高溫側衰減比低溫側更快（非對稱 Gaussian：σ_hot=7 < σ_cold=10）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        from src.scorer import _temperature_score
        # 偏離理想區間相同距離：低溫 18-8=10°C vs 高溫 22+10=32°C
        # 高溫側 sigma=7 衰減更快，所以 32°C 分數應低於 8°C
        score_cold = _temperature_score(8.0)   # 低於理想 10°C
        score_hot  = _temperature_score(32.0)  # 高於理想 10°C
        assert score_hot < score_cold

    # --- rain_score sub-tests ---

    def test_zero_rain_gives_rain_score_100(self) -> None:
        """降雨 0% → rain_score = 100。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=18, rain=0, crowd=5 → crowd_score = 100-(5-1)²*2 = 68
        records = [ComfortScoreRecord(1, "東京", 18.0, 0, 5)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 100*0.3 + 68*0.3 = 90.4
        assert scores[1] == pytest.approx(90.4, abs=0.3)

    def test_100_rain_gives_rain_score_0(self) -> None:
        """降雨 100% → rain_score = 0。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # temp=18, rain=100, crowd=5 → crowd_score=68
        records = [ComfortScoreRecord(6, "東京", 18.0, 100, 5)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 0*0.3 + 68*0.3 = 60.4
        assert scores[6] == pytest.approx(60.4, abs=0.3)

    # --- crowd_score sub-tests (non-linear) ---

    def test_crowd_1_gives_crowd_score_100(self) -> None:
        """crowd_index=1 → crowd_score = 100。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(1, "東京", 18.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 100*0.3 + 100*0.3 = 100.0
        assert scores[1] == pytest.approx(100.0, abs=0.2)

    def test_crowd_5_gives_crowd_score_68(self) -> None:
        """crowd_index=5 → crowd_score = 100 - (5-1)²×2 = 68。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(1, "東京", 18.0, 0, 5)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 100*0.3 + 68*0.3 = 90.4
        assert scores[1] == pytest.approx(90.4, abs=0.3)

    def test_crowd_7_gives_crowd_score_40(self) -> None:
        """crowd_index=7 → crowd_score = 68 - (7-5)×14 = 40。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(1, "東京", 18.0, 0, 7)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 100*0.3 + 40*0.3 = 82.0
        assert scores[1] == pytest.approx(82.0, abs=0.3)

    def test_crowd_9_gives_crowd_score_0(self) -> None:
        """crowd_index=9 → crowd_score = 40 - (9-7)²×13.3 = -13.2 → clip 至 0（重度懲罰）。

        注意：crowd_index 是人潮擁擠程度（1=人少、10=非常擁擠），不是舒適分數。
        crowd_score 是由 _crowd_score() 將擁擠程度轉換後的舒適度子分數（0–100）。
        crowd=9 時公式結果為負數，clip 至 0。
        """
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(4, "東京", 18.0, 0, 9)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # crowd_score = max(0, 40 - (9-7)²×13.3) = max(0, -13.2) = 0
        # comfort = 100*0.4 + 100*0.3 + 0*0.3 = 70.0
        assert scores[4] == pytest.approx(70.0, abs=0.2)

    def test_crowd_10_gives_crowd_score_0(self) -> None:
        """crowd_index=10 → crowd_score = 0（clip）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(4, "東京", 18.0, 0, 10)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        # comfort = 100*0.4 + 100*0.3 + 0*0.3 = 70.0
        assert scores[4] == pytest.approx(70.0, abs=0.2)

    def test_high_crowd_penalized_more_than_low_crowd(self) -> None:
        """非線性懲罰：crowd=9 的分數應明顯低於 crowd=5。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        r_low = analyze_comfort([ComfortScoreRecord(1, "東京", 18.0, 0, 5)])
        r_high = analyze_comfort([ComfortScoreRecord(1, "東京", 18.0, 0, 9)])
        s_low = calculate_comfort_score(r_low)[1]
        s_high = calculate_comfort_score(r_high)[1]
        # crowd=5 → 90.4；crowd=9 → 72.0；差距 > 15 分
        assert (s_low - s_high) > 15.0

    # --- combined formula tests ---

    def test_score_clipped_to_0_100(self) -> None:
        """分數應 clip 至 [0, 100]，不超出範圍。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        records = [ComfortScoreRecord(1, "東京", 18.0, 0, 1)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score(result)
        assert 0.0 <= scores[1] <= 100.0

    def test_empty_comfort_result_all_nan(self) -> None:
        """空舒適度資料應回傳全 NaN。"""
        result = analyze_comfort([])
        scores = calculate_comfort_score(result)
        assert scores.isna().all()

    def test_missing_month_is_nan(self) -> None:
        """無資料月份應為 NaN。"""
        result = _make_comfort_result([(3, "東京", 35, 8)])
        scores = calculate_comfort_score(result)
        assert not pd.isna(scores[3])
        assert pd.isna(scores[1])

    def test_index_covers_all_12_months(self) -> None:
        """結果 index 應涵蓋 1–12 月。"""
        result = _make_comfort_result([(1, "東京", 15, 5)])
        scores = calculate_comfort_score(result)
        assert list(scores.index) == _ALL_MONTHS


# ===========================================================================
# calculate_tci
# ===========================================================================

class TestCalculateTCI:

    def _full_results(self):
        """建立完整 12 個月資料的三個 result。"""
        fare = _make_fare_result({m: 10000 + m * 1000 for m in range(1, 13)})
        rate = _make_rate_result({m: 0.2078 + m * 0.0004 for m in range(1, 13)})
        comfort = _make_comfort_result([
            (m, "東京", 20 + m, 3 + m % 5)
            for m in range(1, 13)
        ])
        return fare, rate, comfort

    def test_returns_score_result(self) -> None:
        """應回傳 ScoreResult dataclass。"""
        from src.models import ScoreResult
        fare, rate, comfort = self._full_results()
        result = calculate_tci(fare, rate, comfort)
        assert isinstance(result, ScoreResult)

    def test_total_score_within_0_to_100(self) -> None:
        """TCI 應在 [0, 100] 範圍內。"""
        fare, rate, comfort = self._full_results()
        result = calculate_tci(fare, rate, comfort)
        valid = result.total_score.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_total_score_rounded_to_1_decimal(self) -> None:
        """TCI 應四捨五入至一位小數。"""
        fare, rate, comfort = self._full_results()
        result = calculate_tci(fare, rate, comfort)
        for val in result.total_score.dropna():
            assert round(float(val), 1) == pytest.approx(float(val), abs=1e-9)

    def test_fare_nan_propagates_to_tci(self) -> None:
        """票價分數為 NaN 的月份，TCI 應為 NaN。"""
        fare = _make_fare_result({1: 10000, 12: 20000})  # 只有 1 月和 12 月
        rate = _make_rate_result({m: 0.2100 for m in range(1, 13)})
        comfort = _make_comfort_result([(m, "東京", 30, 5) for m in range(1, 13)])
        result = calculate_tci(fare, rate, comfort)
        # 月份 2–11 無票價資料 → TCI 應為 NaN
        for m in range(2, 12):
            assert pd.isna(result.total_score[m]), f"月份 {m} 的 TCI 應為 NaN"

    def test_rate_nan_does_not_block_tci(self) -> None:
        """匯率分數為 NaN 時，TCI 仍可計算（以 0 代入加權）。"""
        fare = _make_fare_result({m: 10000 + m * 500 for m in range(1, 13)})
        rate = _make_rate_result({})  # 全部 NaN
        comfort = _make_comfort_result([(m, "東京", 30, 5) for m in range(1, 13)])
        result = calculate_tci(fare, rate, comfort)
        # 票價有資料 → TCI 不應全為 NaN
        assert not result.total_score.isna().all()

    def test_comfort_nan_does_not_block_tci(self) -> None:
        """舒適度分數為 NaN 時，TCI 仍可計算（以 0 代入加權）。"""
        fare = _make_fare_result({m: 10000 + m * 500 for m in range(1, 13)})
        rate = _make_rate_result({m: 0.2100 for m in range(1, 13)})
        comfort = analyze_comfort([])  # 空舒適度
        result = calculate_tci(fare, rate, comfort)
        assert not result.total_score.isna().all()

    def test_weights_sum_to_correct_tci(self) -> None:
        """手動驗證 TCI 加權公式正確性（fare 40%, comfort 50%, rate 10%）。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        # fare: 月份 1 (min=10000) → 100 分；月份 12 (max=20000) → 0 分
        # rate: 月份 1 (min=0.2000) → 100 分（最低匯率最划算）；月份 12 (max=0.2100) → 0 分
        # comfort: 月份 1 temp=18°C（理想區間）, rain=0%, crowd=1 → comfort=100.0
        fare = _make_fare_result({1: 10000, 12: 20000})
        rate = _make_rate_result({1: 0.2000, 12: 0.2100})
        comfort_records = [ComfortScoreRecord(1, "東京", 18.0, 0, 1)]
        comfort = analyze_comfort(comfort_records)

        result = calculate_tci(fare, rate, comfort)

        # 月份 1: fare=100, rate=100, comfort=100
        # TCI = 100×0.4 + 100×0.5 + 100×0.1 = 40 + 50 + 10 = 100.0
        assert result.total_score[1] == pytest.approx(100.0, abs=0.2)

    def test_all_scores_have_correct_index(self) -> None:
        """所有分數 Series 的 index 應涵蓋 1–12 月。"""
        fare, rate, comfort = self._full_results()
        result = calculate_tci(fare, rate, comfort)
        assert list(result.fare_score.index) == _ALL_MONTHS
        assert list(result.rate_score.index) == _ALL_MONTHS
        assert list(result.comfort_score.index) == _ALL_MONTHS
        assert list(result.total_score.index) == _ALL_MONTHS

    def test_best_month_has_highest_tci(self) -> None:
        """TCI 最高的月份應可正確識別。"""
        fare, rate, comfort = self._full_results()
        result = calculate_tci(fare, rate, comfort)
        valid = result.total_score.dropna()
        best_month = int(valid.idxmax())
        assert result.total_score[best_month] == valid.max()

    def test_empty_all_inputs_returns_nan_tci(self) -> None:
        """三個輸入均為空時，TCI 應全為 NaN。"""
        fare = _make_fare_result({})
        rate = _make_rate_result({})
        comfort = analyze_comfort([])
        result = calculate_tci(fare, rate, comfort)
        assert result.total_score.isna().all()


# ===========================================================================
# calculate_comfort_score_for_city / calculate_tci_for_city
# ===========================================================================

class TestPerCityScoring:

    def test_comfort_score_for_city_uses_only_that_city(self) -> None:
        """comfort_score_for_city 應只使用指定城市的資料，不受其他城市影響。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        from src.scorer import calculate_comfort_score_for_city
        records = [
            ComfortScoreRecord(1, "東京", 6.1, 15, 5),   # 低溫
            ComfortScoreRecord(1, "沖繩", 17.2, 20, 4),  # 舒適
        ]
        result = analyze_comfort(records)
        tokyo_score = calculate_comfort_score_for_city(result, "東京")[1]
        okinawa_score = calculate_comfort_score_for_city(result, "沖繩")[1]
        # 沖繩 1 月氣溫 17.2°C（理想區間），東京 6.1°C（低溫扣分）
        # 沖繩分數應高於東京
        assert okinawa_score > tokyo_score

    def test_comfort_score_for_city_unknown_city_returns_nan(self) -> None:
        """不存在的城市應回傳全 NaN。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        from src.scorer import calculate_comfort_score_for_city
        records = [ComfortScoreRecord(1, "東京", 6.1, 15, 5)]
        result = analyze_comfort(records)
        scores = calculate_comfort_score_for_city(result, "不存在城市")
        assert scores.isna().all()

    def test_comfort_score_for_city_sapporo_winter_penalized(self) -> None:
        """札幌冬季（−3.2°C）應被明顯懲罰，分數低於東京。"""
        from src.models import ComfortScoreRecord
        from src.analyzer import analyze_comfort
        from src.scorer import calculate_comfort_score_for_city
        records = [
            ComfortScoreRecord(1, "東京", 6.1, 15, 5),
            ComfortScoreRecord(1, "札幌", -3.2, 40, 3),
        ]
        result = analyze_comfort(records)
        tokyo = calculate_comfort_score_for_city(result, "東京")[1]
        sapporo = calculate_comfort_score_for_city(result, "札幌")[1]
        # 新公式（非對稱 Gaussian）：
        # 東京 6.1°C → temp_score ≈ 47（偏離 18°C 約 12°C，σ_cold=10）
        # 札幌 -3.2°C → temp_score ≈ 4（偏離 18°C 約 21°C，σ_cold=10）
        # 札幌分數應明顯低於東京
        assert sapporo < tokyo

    def test_tci_for_city_returns_score_result(self) -> None:
        """calculate_tci_for_city 應回傳 ScoreResult。"""
        from src.models import ComfortScoreRecord, FareRecord, ScoreResult
        from src.analyzer import analyze_comfort, analyze_fares_for_city
        from src.scorer import calculate_tci_for_city
        comfort_records = [ComfortScoreRecord(m, "東京", 15.0, 20, 4) for m in range(1, 13)]
        fare_records = [
            FareRecord(f"2024-{m:02d}-01", "CI", "TPE", "東京", 15000 + m * 100)
            for m in range(1, 13)
        ]
        comfort = analyze_comfort(comfort_records)
        city_fare = analyze_fares_for_city(fare_records, "東京")
        rate = _make_rate_result({m: 0.2100 for m in range(1, 13)})
        result = calculate_tci_for_city(city_fare, rate, comfort, "東京")
        assert isinstance(result, ScoreResult)

    def test_tci_for_city_rate_score_shared(self) -> None:
        """不同城市的 rate_score 應相同（匯率不分城市）。"""
        from src.models import ComfortScoreRecord, FareRecord
        from src.analyzer import analyze_comfort, analyze_fares_for_city
        from src.scorer import calculate_tci_for_city
        comfort_records = [
            ComfortScoreRecord(m, "東京", 15.0, 20, 4) for m in range(1, 13)
        ] + [
            ComfortScoreRecord(m, "沖繩", 22.0, 25, 4) for m in range(1, 13)
        ]
        fare_records = [
            FareRecord(f"2024-{m:02d}-01", "CI", "TPE", "東京", 15000 + m * 100)
            for m in range(1, 13)
        ] + [
            FareRecord(f"2024-{m:02d}-01", "CI", "TPE", "沖繩", 14000 + m * 100)
            for m in range(1, 13)
        ]
        comfort = analyze_comfort(comfort_records)
        rate = _make_rate_result({m: 0.2078 + m * 0.0004 for m in range(1, 13)})
        tokyo_fare = analyze_fares_for_city(fare_records, "東京")
        okinawa_fare = analyze_fares_for_city(fare_records, "沖繩")
        tokyo_result = calculate_tci_for_city(tokyo_fare, rate, comfort, "東京")
        okinawa_result = calculate_tci_for_city(okinawa_fare, rate, comfort, "沖繩")
        # rate_score 應完全相同（匯率不分城市）
        import pandas as pd
        pd.testing.assert_series_equal(
            tokyo_result.rate_score.fillna(-1),
            okinawa_result.rate_score.fillna(-1),
        )

    def test_calculate_tci_all_cities_returns_all_cities(self) -> None:
        """calculate_tci_all_cities 應回傳所有城市的 ScoreResult。"""
        from src.models import ComfortScoreRecord, FareRecord
        from src.analyzer import analyze_comfort
        from src.scorer import calculate_tci_all_cities
        cities = ["東京", "大阪", "福岡"]
        comfort_records = [
            ComfortScoreRecord(m, city, 15.0, 20, 4)
            for city in cities for m in range(1, 13)
        ]
        fare_records = [
            FareRecord(f"2024-{m:02d}-01", "CI", "TPE", city, 15000 + m * 100)
            for city in cities for m in range(1, 13)
        ]
        comfort = analyze_comfort(comfort_records)
        rate = _make_rate_result({m: 0.2100 for m in range(1, 13)})
        results = calculate_tci_all_cities(fare_records, rate, comfort)
        assert set(results.keys()) == set(cities)

    def test_different_cities_have_different_comfort_scores(self) -> None:
        """不同城市因氣候不同，comfort_score 應有差異。"""
        from src.models import ComfortScoreRecord, FareRecord
        from src.analyzer import analyze_comfort
        from src.scorer import calculate_tci_all_cities
        comfort_records = [
            ComfortScoreRecord(7, "東京", 29.4, 55, 6),   # 高溫高雨
            ComfortScoreRecord(7, "札幌", 23.5, 48, 6),   # 舒適
        ]
        fare_records = [
            FareRecord("2024-07-01", "CI", "TPE", "東京", 15000),
            FareRecord("2024-07-01", "CI", "TPE", "札幌", 15000),
        ]
        comfort = analyze_comfort(comfort_records)
        rate = _make_rate_result({7: 0.2100})
        results = calculate_tci_all_cities(fare_records, rate, comfort)
        tokyo_comfort = results["東京"].comfort_score[7]
        sapporo_comfort = results["札幌"].comfort_score[7]
        # 7 月札幌（23.5°C）比東京（29.4°C）舒適
        assert sapporo_comfort > tokyo_comfort
