"""
src/fetcher.py
==============
自動資料抓取模組（Production 版）。

公開函式
--------
    fetch_exchange_rates(year)  → pd.DataFrame  (date, jpy_twd_rate)
    fetch_comfort_scores(year)  → pd.DataFrame  (year, month, city, avg_temp_c,
                                                  rain_probability_pct, crowd_index)

資料來源
--------
匯率：臺灣銀行每日匯率 CSV
    https://rate.bot.com.tw/xrt/flcsv/0/YYYY-MM-DD
    取「即期賣出」匯率（欄位索引 [13]，UTF-8-BOM 解碼）

氣候：日本氣象廳（JMA）月別統計資料
    https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php
    ?prec_no={prec_no}&block_no={block_no}&year={year}
    表格：12 列（月份）× 28 欄（MultiIndex 3 層）
    取月均氣溫 ('気温(℃)','平均','日平均') 與月降水量 ('降水量(mm)','合計','合計')

crowd_index：旅遊旺季熱度推估模型（規則式，非即時人流資料）

Debug 模式
----------
設定環境變數 FETCHER_DEBUG=1 或在程式碼中設 DEBUG=True 可啟用詳細診斷輸出。
"""

from __future__ import annotations

import calendar
import os
import re
import time
from io import StringIO
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Debug 開關
# ---------------------------------------------------------------------------

# 設定 FETCHER_DEBUG=1 環境變數，或直接改此常數為 True
DEBUG: bool = os.environ.get("FETCHER_DEBUG", "0") == "1"


# ---------------------------------------------------------------------------
# Logging 輔助
# ---------------------------------------------------------------------------

def _info(msg: str) -> None:
    """輸出 INFO 層級訊息（正式模式也顯示）。"""
    print(f"[INFO] {msg}")


def _debug(msg: str) -> None:
    """輸出 DEBUG 層級訊息（僅 DEBUG=True 時顯示）。"""
    if DEBUG:
        print(f"[DEBUG] {msg}")


def _warning(msg: str) -> None:
    """輸出 WARNING 層級訊息（正式模式也顯示）。"""
    print(f"[WARNING] {msg}")


def _error(msg: str) -> None:
    """輸出 ERROR 層級訊息（正式模式也顯示）。"""
    print(f"[ERROR] {msg}")


# ---------------------------------------------------------------------------
# 自訂例外
# ---------------------------------------------------------------------------

class FetchError(Exception):
    """資料抓取失敗時拋出（連線失敗、HTML 結構變更、資料不存在等）。"""
    pass


# ---------------------------------------------------------------------------
# HTTP Session（共用，避免重複建立連線）
# ---------------------------------------------------------------------------

_BOT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

_JMA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://www.data.jma.go.jp/stats/etrn/index.php",
}


def _get_session():
    """建立並回傳 requests.Session（含共用 headers）。"""
    try:
        import requests
    except ImportError:
        raise FetchError("缺少 requests 套件，請執行：pip install requests")
    return requests.Session()


# ---------------------------------------------------------------------------
# 城市設定（JMA 觀測站代碼）
# ---------------------------------------------------------------------------

# JMA 各城市的觀測站代碼（prec_no=都道府縣代碼, block_no=觀測站代碼）
# 分析城市：東京、大阪、福岡、札幌、沖繩（那霸）
_JMA_STATIONS: dict[str, dict[str, str]] = {
    "東京": {"prec_no": "44", "block_no": "47662"},
    "大阪": {"prec_no": "62", "block_no": "47772"},
    "福岡": {"prec_no": "82", "block_no": "47807"},
    "札幌": {"prec_no": "14", "block_no": "47412"},
    "沖繩": {"prec_no": "91", "block_no": "47936"},  # 那霸觀測站
}

_CITIES = list(_JMA_STATIONS.keys())

# ---------------------------------------------------------------------------
# 旅遊旺季熱度推估模型（crowd_index）
# ---------------------------------------------------------------------------
# crowd_index 為旅遊熱度推估指標，不是即時人流監測資料。
# 依據：日本觀光旺季規律、國定假日、季節性活動評估 1–10 分。

_BASE_CROWD_INDEX: dict[int, int] = {
    1: 6,   # 年末年始後期
    2: 3,   # 淡季
    3: 5,   # 春假、梅花季
    4: 9,   # 櫻花季（全年最旺）
    5: 8,   # 黃金週
    6: 3,   # 梅雨淡季
    7: 6,   # 暑假開始
    8: 7,   # 暑假旺季
    9: 5,   # 暑假結束
    10: 6,  # 楓葉季開始
    11: 8,  # 楓葉季高峰
    12: 6,  # 年末年始準備
}

_CITY_CROWD_ADJUSTMENT: dict[str, dict[int, int]] = {
    "東京": {4: 0, 11: 0},
    "大阪": {4: 0, 11: 1},
    "福岡": {4: -1, 8: -1, 11: -1},
    "札幌": {2: 2, 7: 1, 8: 1, 12: 1},
    "沖繩": {7: 1, 8: 1, 4: -1, 11: -1},  # 暑假旺季高，春秋相對較低
}


def _get_crowd_index(city: str, month: int) -> int:
    """計算指定城市、月份的旅遊熱度推估指數（1–10）。"""
    base = _BASE_CROWD_INDEX.get(month, 5)
    adj = _CITY_CROWD_ADJUSTMENT.get(city, {}).get(month, 0)
    return max(1, min(10, base + adj))


# ---------------------------------------------------------------------------
# 匯率抓取（臺灣銀行每日 CSV）
# ---------------------------------------------------------------------------

# 每月抽取的日期清單。
# 多個日期確保假日較多的月份仍能取到至少一筆資料。
_BOT_SAMPLE_DAYS = [2, 5, 8, 12, 15, 19, 22, 26]

# JMA 欄位 mapping（MultiIndex 3 層）
_JMA_COL_MONTH = [("月", "月", "月"), "月"]
_JMA_COL_TEMP  = [("気温(℃)", "平均", "日平均"), ("気温(℃)", "平均", "平均"), "日平均"]
_JMA_COL_RAIN  = [("降水量(mm)", "合計", "合計"), "合計"]

# 降水量 mm → 降雨機率 % 的正規化係數（300mm = 100%）
_RAIN_MM_TO_PCT_DIVISOR = 3.0

# 氣候學估算降雨機率（當 JMA 降水量資料不可用時）
_FALLBACK_RAIN_PCT: dict[int, int] = {
    1: 20, 2: 22, 3: 30, 4: 35,
    5: 35, 6: 65, 7: 60, 8: 50,
    9: 50, 10: 35, 11: 28, 12: 22,
}


def fetch_exchange_rates(year: int) -> pd.DataFrame:
    """
    從臺灣銀行每日匯率 CSV 抓取指定年度的 JPY/TWD 即期賣出匯率。

    端點：https://rate.bot.com.tw/xrt/flcsv/0/YYYY-MM-DD
    每月抽取 _BOT_SAMPLE_DAYS 中的日期，假日回傳 text/plain 時直接跳過（正常現象）。

    Parameters
    ----------
    year : int
        目標年度（例：2025）。

    Returns
    -------
    pd.DataFrame
        columns: date (YYYY-MM-DD), jpy_twd_rate (float, 4 位小數)
        依日期升冪排序。

    Raises
    ------
    FetchError
        連線失敗或全年無法取得任何資料時。
    """
    _info(f"Fetching exchange rates from Bank of Taiwan ({year})...")

    session = _get_session()
    session.headers.update(_BOT_HEADERS)

    all_rows: list[dict] = []
    months_with_data: list[int] = []

    for month in range(1, 13):
        month_rows = _fetch_bot_month(session, year, month)
        if month_rows:
            all_rows.extend(month_rows)
            months_with_data.append(month)
        else:
            _debug(f"No data for {year}-{month:02d} (all sample days were holidays or unavailable)")

    session.close()

    missing = [m for m in range(1, 13) if m not in months_with_data]
    if missing:
        _warning(
            f"Exchange rate data missing for {len(missing)} month(s): "
            + ", ".join(f"{year}-{m:02d}" for m in missing)
        )

    if not all_rows:
        raise FetchError(
            f"No JPY/TWD exchange rate data available for {year}.\n"
            f"  Sample URL: https://rate.bot.com.tw/xrt/flcsv/0/{year}-01-02\n"
            f"  Possible causes: site maintenance, data not yet available, or network issue."
        )

    df = pd.DataFrame(all_rows, columns=["date", "jpy_twd_rate"])
    df = df.sort_values("date").reset_index(drop=True)
    df["jpy_twd_rate"] = df["jpy_twd_rate"].round(4)

    _info(f"Exchange rates fetched: {len(df)} records ({year}, {len(months_with_data)}/12 months)")
    return df


def _fetch_bot_month(
    session,
    year: int,
    month: int,
) -> list[dict]:
    """
    抓取臺灣銀行指定年月的匯率資料（嘗試 _BOT_SAMPLE_DAYS 中的每個日期）。

    假日回傳 text/plain 是正常現象，直接跳過不視為錯誤。
    只有真正的連線失敗才拋出 FetchError。
    """
    try:
        import requests as req_lib
    except ImportError:
        raise FetchError("缺少 requests 套件，請執行：pip install requests")

    last_day = calendar.monthrange(year, month)[1]
    month_rows: list[dict] = []

    for day in _BOT_SAMPLE_DAYS:
        if day > last_day:
            continue

        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        url = f"https://rate.bot.com.tw/xrt/flcsv/0/{date_str}"

        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except req_lib.exceptions.ConnectionError as exc:
            raise FetchError(f"Bank of Taiwan connection failed ({date_str}): {exc}")
        except req_lib.exceptions.Timeout:
            raise FetchError(f"Bank of Taiwan request timed out ({date_str})")
        except req_lib.exceptions.HTTPError:
            _debug(f"BOT {date_str}: HTTP {resp.status_code}, skipping")
            continue
        except Exception as exc:
            raise FetchError(f"Bank of Taiwan request failed ({date_str}): {exc}")

        ct = resp.headers.get("Content-Type", "")
        if "text/csv" not in ct:
            # 假日或維護中，屬正常現象，靜默跳過
            _debug(f"BOT {date_str}: non-CSV response ({ct}), holiday or maintenance")
            continue

        # 強制以 UTF-8-BOM 解碼（臺灣銀行 CSV 使用 UTF-8 with BOM）
        csv_text = resp.content.decode("utf-8-sig")
        rate = _parse_bot_jpy_spot(csv_text)

        if rate is not None:
            month_rows.append({"date": date_str, "jpy_twd_rate": rate})
            _debug(f"BOT {date_str}: JPY spot sell = {rate}")
        else:
            _warning(f"BOT {date_str}: failed to parse JPY spot rate from CSV")

        time.sleep(0.3)

    return month_rows


def _parse_bot_jpy_spot(csv_text: str) -> Optional[float]:
    """
    從臺灣銀行 CSV 文字中提取 JPY 即期賣出匯率。

    CSV 格式（已確認穩定）：
        JPY, 本行買入, [2]現金買入, [3]即期買入, ...(7欄)...,
             本行賣出, [12]現金賣出, [13]即期賣出, ...

    即期賣出 = 欄位索引 [13]（0-based）。
    若結構異常，嘗試動態定位「本行賣出」後的第 2 個欄位。
    """
    for line in csv_text.splitlines():
        line = line.strip()
        if not line.startswith("JPY"):
            continue

        parts = line.split(",")

        # 快速路徑：已知穩定格式
        if (len(parts) >= 14
                and parts[1].strip() == "本行買入"
                and parts[11].strip() == "本行賣出"):
            val = parts[13].strip()
            try:
                rate = float(val)
                if rate > 0:
                    return rate
            except ValueError:
                _debug(f"BOT parse: cannot convert spot sell value {val!r}")
            return None

        # 備援路徑：動態定位「本行賣出」
        _debug(f"BOT parse: unexpected CSV structure, trying dynamic lookup")
        try:
            sell_idx = parts.index("本行賣出")
            spot_idx = sell_idx + 2  # 現金賣出 +1, 即期賣出 +2
            if spot_idx < len(parts):
                rate = float(parts[spot_idx].strip())
                if rate > 0:
                    return rate
        except (ValueError, IndexError):
            pass

        _warning(f"BOT parse: cannot locate JPY spot sell rate in CSV line")
        return None

    return None


# ---------------------------------------------------------------------------
# 氣候資料抓取（JMA monthly_s1.php）
# ---------------------------------------------------------------------------

def fetch_comfort_scores(year: int) -> pd.DataFrame:
    """
    從日本氣象廳（JMA）抓取指定年度各城市的月均氣溫與月降水量，
    並結合旅遊旺季熱度推估模型產生 comfort_scores 資料。

    端點：https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php
          ?prec_no={prec_no}&block_no={block_no}&year={year}

    表格格式（MultiIndex 3 層，shape=(12, 28)）：
        ('月', '月', '月')              → 月份（1–12）
        ('気温(℃)', '平均', '日平均')    → 月均氣溫（°C）
        ('降水量(mm)', '合計', '合計')    → 月降水量（mm）

    Parameters
    ----------
    year : int
        目標年度（例：2025）。

    Returns
    -------
    pd.DataFrame
        columns: year, month, city, avg_temp_c, rain_probability_pct, crowd_index
        共 城市數 × 12 筆資料。

    Raises
    ------
    FetchError
        所有城市均無法取得資料時。

    Notes
    -----
    rain_probability_pct = min(100, int(mm / 3.0))
        0mm → 0%，300mm → 100%（符合日本月降水量範圍）
    crowd_index 為旅遊旺季熱度推估指標，不是即時人流監測資料。
    """
    _info(f"Fetching climate data from JMA ({year})...")

    session = _get_session()
    session.headers.update(_JMA_HEADERS)

    all_rows: list[dict] = []
    failed_cities: list[str] = []
    total = len(_JMA_STATIONS)

    for idx, (city, station) in enumerate(_JMA_STATIONS.items(), start=1):
        _info(f"  [{idx}/{total}] {city}...")
        try:
            city_rows = _fetch_jma_city(session, city, station, year)
            all_rows.extend(city_rows)
            _debug(f"JMA {city}: {len(city_rows)} records parsed")
        except FetchError as exc:
            _warning(f"JMA {city}: fetch failed — {exc}")
            failed_cities.append(city)

        if idx < total:
            time.sleep(0.8)

    session.close()

    if not all_rows:
        raise FetchError(
            f"No JMA climate data available for any city ({year}).\n"
            f"  Please check: https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php"
        )

    if failed_cities:
        _warning(f"JMA: failed cities not included in output: {failed_cities}")

    df = pd.DataFrame(all_rows)
    df = df.sort_values(["city", "month"]).reset_index(drop=True)

    _info(f"Climate data fetched: {len(df)} records ({year}, {len(df) // 12} cities)")
    return df


def _fetch_jma_city(
    session,
    city: str,
    station: dict[str, str],
    year: int,
) -> list[dict]:
    """
    抓取 JMA 指定城市、年度的月別氣候資料（monthly_s1.php）。

    monthly_s1.php 是「單年詳細頁」：
        - 12 列（月份 1–12）× 28 欄（氣象要素）
        - 欄位為 3 層 MultiIndex
    """
    try:
        import requests as req_lib
    except ImportError:
        raise FetchError("缺少 requests 套件，請執行：pip install requests")

    url = "https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php"
    params = {
        "prec_no":  station["prec_no"],
        "block_no": station["block_no"],
        "year":     str(year),
        "month":    "",
        "day":      "",
        "view":     "",
    }

    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except req_lib.exceptions.ConnectionError as exc:
        raise FetchError(f"JMA connection failed ({city}): {exc}")
    except req_lib.exceptions.Timeout:
        raise FetchError(f"JMA request timed out ({city})")
    except req_lib.exceptions.HTTPError:
        raise FetchError(f"JMA HTTP error ({city}): {resp.status_code}")
    except Exception as exc:
        raise FetchError(f"JMA request failed ({city}): {exc}")

    _debug(f"JMA {city}: HTTP {resp.status_code}, url={resp.url}")

    return _parse_jma_monthly_s1(resp.text, city, year)


def _parse_jma_monthly_s1(html: str, city: str, year: int) -> list[dict]:
    """
    解析 JMA monthly_s1.php 頁面，提取月均氣溫與月降水量。

    表格結構（MultiIndex 3 層，已確認穩定）：
        shape = (12, 28)
        ('月', '月', '月')              → 月份
        ('気温(℃)', '平均', '日平均')    → 月均氣溫
        ('降水量(mm)', '合計', '合計')    → 月降水量 mm
    """
    try:
        tables = pd.read_html(StringIO(html))
    except Exception as exc:
        raise FetchError(f"JMA HTML parse failed ({city}, {year}): {exc}")

    if not tables:
        raise FetchError(f"JMA: no tables found in response ({city}, {year})")

    df = tables[0]
    _debug(f"JMA {city}: table shape={df.shape}, cols[:4]={list(df.columns)[:4]}")

    if df.shape[0] < 12:
        raise FetchError(
            f"JMA table has too few rows ({city}, {year}): "
            f"expected 12, got {df.shape[0]}"
        )

    # 定位目標欄位
    month_col = _locate_col(df, _JMA_COL_MONTH)
    temp_col  = _locate_col(df, _JMA_COL_TEMP)
    rain_col  = _locate_col(df, _JMA_COL_RAIN)

    _debug(f"JMA {city}: month={month_col}, temp={temp_col}, rain={rain_col}")

    if month_col is None:
        raise FetchError(
            f"JMA: month column not found ({city}, {year}). "
            f"Columns: {list(df.columns)[:8]}"
        )
    if temp_col is None:
        raise FetchError(
            f"JMA: temperature column not found ({city}, {year}). "
            f"Columns: {list(df.columns)}"
        )

    return _extract_jma_rows(df, city, year, month_col, temp_col, rain_col)


def _extract_jma_rows(
    df: pd.DataFrame,
    city: str,
    year: int,
    month_col: object,
    temp_col: object,
    rain_col: Optional[object],
) -> list[dict]:
    """
    從 JMA 表格中逐列提取月份、氣溫、降水量，組裝成 dict list。
    """
    rows: list[dict] = []

    for _, row in df.iterrows():
        month = _parse_int_month(row[month_col])
        if month is None:
            continue

        temp = _parse_jma_float(row[temp_col])
        if temp is None:
            _debug(f"JMA {city} month={month}: temperature parse failed ({row[temp_col]!r})")
            continue

        # 降水量 mm → 降雨機率 %
        rainfall_mm = _parse_jma_float(row[rain_col]) if rain_col is not None else None
        if rainfall_mm is not None and rainfall_mm >= 0:
            rain_pct = min(100, int(round(rainfall_mm / _RAIN_MM_TO_PCT_DIVISOR)))
        else:
            rain_pct = _FALLBACK_RAIN_PCT.get(month, 30)
            _debug(f"JMA {city} month={month}: rainfall unavailable, using fallback {rain_pct}%")

        rows.append({
            "year":                year,
            "month":               month,
            "city":                city,
            "avg_temp_c":          round(temp, 1),
            "rain_probability_pct": rain_pct,
            "crowd_index":         _get_crowd_index(city, month),
        })

    if len(rows) < 10:
        raise FetchError(
            f"JMA: insufficient data ({city}, {year}): "
            f"got {len(rows)} rows, expected 12"
        )

    return rows


# ---------------------------------------------------------------------------
# 欄位定位輔助（JMA MultiIndex）
# ---------------------------------------------------------------------------

def _locate_col(df: pd.DataFrame, candidates: list) -> Optional[object]:
    """
    在 DataFrame 欄位中尋找候選欄位名稱。

    支援：
    - tuple（MultiIndex 完全匹配）
    - tuple（MultiIndex 部分匹配，空字串視為萬用）
    - 字串（在 tuple 欄位的任一層中尋找）
    - 最後備援：欄位名稱字串包含候選關鍵字
    """
    cols = list(df.columns)

    for candidate in candidates:
        # 完全匹配
        if candidate in cols:
            return candidate

        if isinstance(candidate, tuple):
            # tuple 部分匹配（空字串層視為萬用）
            for col in cols:
                if isinstance(col, tuple) and len(col) == len(candidate):
                    if all(
                        c == "" or str(col[i]).strip() == str(c).strip()
                        for i, c in enumerate(candidate)
                    ):
                        return col
        elif isinstance(candidate, str):
            # 字串：在 tuple 欄位的任一層中尋找
            for col in cols:
                if isinstance(col, tuple):
                    if any(str(layer).strip() == candidate for layer in col):
                        return col
                elif str(col).strip() == candidate:
                    return col

    # 備援：欄位名稱字串包含第一個候選的關鍵字
    if candidates:
        first = candidates[0]
        keyword = first[0] if isinstance(first, tuple) else str(first)
        for col in cols:
            if keyword in str(col):
                return col

    return None


# ---------------------------------------------------------------------------
# 數值解析輔助
# ---------------------------------------------------------------------------

def _parse_int_month(val) -> Optional[int]:
    """解析月份值（1–12），無效值回傳 None。"""
    try:
        month = int(float(str(val)))
        return month if 1 <= month <= 12 else None
    except (ValueError, TypeError):
        return None


def _parse_jma_float(val) -> Optional[float]:
    """
    解析 JMA 表格中的數值。

    處理 JMA 特殊符號：
        '--', '×', '///', '' → None（無資料）
        '12.3)' → 12.3（移除括號殘留字元）
    """
    s = str(val).strip()
    if s in ("--", "×", "///", "", "nan", "NaN", "None", "-"):
        return None
    # 移除括號殘留字元（JMA 有時在數值後附加 ')' 或 ']'）
    s = re.sub(r"[)\]]", "", s).strip()
    # 保留負號與小數點，移除其他非數字字元
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None
