"""
src/data_loader.py
==================
CSV 資料載入模組。

提供三個公開函式：
    load_fares(path)           → list[FareRecord]
    load_exchange_rates(path)  → list[ExchangeRateRecord]
    load_comfort_scores(path)  → list[ComfortScoreRecord]

行為規則
--------
- 檔案不存在或必要欄位缺失 → 輸出 [錯誤] 至 stderr，sys.exit(1)
- 單列資料不合法            → 輸出 [警告] 至 stderr，略過該列，繼續執行
- 所有 CSV 以 UTF-8 讀取
- 警告訊息包含 CSV 列號（從 2 開始計，含標頭列）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from .models import (
    ComfortScoreRecord,
    ExchangeRateRecord,
    FareRecord,
)

# ---------------------------------------------------------------------------
# 必要欄位定義
# ---------------------------------------------------------------------------

_FARES_REQUIRED_COLS: list[str] = [
    "date",
    "airline",
    "origin",
    "destination",
    "roundtrip_fare_twd",
]

_RATES_REQUIRED_COLS: list[str] = [
    "date",
    "jpy_twd_rate",
]

_COMFORT_REQUIRED_COLS: list[str] = [
    "month",
    "city",
    "avg_temp_c",
    "rain_probability_pct",
    "crowd_index",
]

# comfort_scores.csv 在加入 year 欄位後的新格式必要欄位
# year 欄位為選填（向後相容舊格式）
_COMFORT_REQUIRED_COLS_NEW: list[str] = [
    "year",
    "month",
    "city",
    "avg_temp_c",
    "rain_probability_pct",
    "crowd_index",
]


# ---------------------------------------------------------------------------
# 內部輔助函式
# ---------------------------------------------------------------------------

def _read_csv(path: Path, required_cols: list[str]) -> pd.DataFrame:
    """
    讀取 CSV 並驗證必要欄位是否存在。

    Parameters
    ----------
    path : Path
        CSV 檔案路徑。
    required_cols : list[str]
        必要欄位名稱清單。

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    SystemExit(1)
        檔案不存在或必要欄位缺失時。
    """
    filename = path.name

    # 1. 檔案存在性檢查
    if not path.exists():
        print(
            f"[錯誤] 找不到檔案：{path.resolve()}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. 讀取 CSV（UTF-8）
    try:
        df = pd.read_csv(path, encoding="utf-8", dtype=str)
    except Exception as exc:
        print(
            f"[錯誤] 無法讀取 {filename}：{exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. 必要欄位檢查
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(
            f"[錯誤] {filename} 缺少必要欄位：{missing_cols}",
            file=sys.stderr,
        )
        sys.exit(1)

    return df


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    """將 pandas Series 轉為 dict，並將 pandas NA / NaN 轉為 None。"""
    result: dict[str, Any] = {}
    for k, v in row.items():
        if pd.isna(v):
            result[str(k)] = None
        else:
            result[str(k)] = v
    return result


def _warn(filename: str, row_num: int, reason: str) -> None:
    """輸出標準格式的警告訊息至 stderr。"""
    print(
        f"[警告] {filename} 第 {row_num} 列：{reason}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# 公開載入函式
# ---------------------------------------------------------------------------

def load_fares(path: str | Path) -> list[FareRecord]:
    """
    載入 fares.csv 並回傳有效的 FareRecord 清單。

    Parameters
    ----------
    path : str | Path
        fares.csv 的檔案路徑。

    Returns
    -------
    list[FareRecord]
        所有通過驗證的票價記錄。無效列會被略過並輸出警告。

    Raises
    ------
    SystemExit(1)
        檔案不存在或必要欄位缺失時。

    Examples
    --------
    >>> records = load_fares("data/fares.csv")
    >>> records[0].airline
    'CI'
    """
    path = Path(path)
    filename = path.name
    df = _read_csv(path, _FARES_REQUIRED_COLS)

    records: list[FareRecord] = []

    for idx, row in df.iterrows():
        # CSV 列號從 2 開始（第 1 列為標頭）
        row_num = int(idx) + 2  # type: ignore[arg-type]
        data = _row_to_dict(row)

        # 缺失值快速檢查（None 表示 CSV 中為空白）
        for col in _FARES_REQUIRED_COLS:
            if data.get(col) is None:
                _warn(filename, row_num, f"{col} 為空值")
                break
        else:
            # 所有必要欄位均有值，嘗試建立 dataclass
            try:
                record = FareRecord.from_dict(data)
                records.append(record)
            except (ValueError, KeyError) as exc:
                _warn(filename, row_num, str(exc))

    return records


def load_exchange_rates(path: str | Path) -> list[ExchangeRateRecord]:
    """
    載入 exchange_rates.csv 並回傳有效的 ExchangeRateRecord 清單。

    Parameters
    ----------
    path : str | Path
        exchange_rates.csv 的檔案路徑。

    Returns
    -------
    list[ExchangeRateRecord]
        所有通過驗證的匯率記錄。無效列會被略過並輸出警告。

    Raises
    ------
    SystemExit(1)
        檔案不存在或必要欄位缺失時。

    Examples
    --------
    >>> records = load_exchange_rates("data/exchange_rates.csv")
    >>> records[0].jpy_twd_rate
    0.2105
    """
    path = Path(path)
    filename = path.name
    df = _read_csv(path, _RATES_REQUIRED_COLS)

    records: list[ExchangeRateRecord] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # type: ignore[arg-type]
        data = _row_to_dict(row)

        for col in _RATES_REQUIRED_COLS:
            if data.get(col) is None:
                _warn(filename, row_num, f"{col} 為空值")
                break
        else:
            try:
                record = ExchangeRateRecord.from_dict(data)
                records.append(record)
            except (ValueError, KeyError) as exc:
                _warn(filename, row_num, str(exc))

    return records


def load_comfort_scores(path: str | Path) -> list[ComfortScoreRecord]:
    """
    載入 comfort_scores.csv 並回傳有效的 ComfortScoreRecord 清單。

    支援兩種格式：
    - 舊格式（向後相容）：month, city, avg_temp_c, rain_probability_pct, crowd_index
    - 新格式（--update-data 產生）：year, month, city, avg_temp_c, rain_probability_pct, crowd_index

    year 欄位為選填，若存在則讀取但不影響分析邏輯。

    Parameters
    ----------
    path : str | Path
        comfort_scores.csv 的檔案路徑。

    Returns
    -------
    list[ComfortScoreRecord]
        所有通過驗證的舒適度記錄。無效列會被略過並輸出警告。

    Raises
    ------
    SystemExit(1)
        檔案不存在或必要欄位缺失時。

    Examples
    --------
    >>> records = load_comfort_scores("data/comfort_scores.csv")
    >>> records[0].city
    '東京'
    """
    path = Path(path)
    filename = path.name
    df = _read_csv(path, _COMFORT_REQUIRED_COLS)

    records: list[ComfortScoreRecord] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # type: ignore[arg-type]
        data = _row_to_dict(row)

        for col in _COMFORT_REQUIRED_COLS:
            if data.get(col) is None:
                _warn(filename, row_num, f"{col} 為空值")
                break
        else:
            try:
                record = ComfortScoreRecord.from_dict(data)
                records.append(record)
            except (ValueError, KeyError) as exc:
                _warn(filename, row_num, str(exc))

    return records
