"""
日本旅遊最佳出發時機分析 Dashboard
====================================
Entry point.

Usage
-----
    python main.py
    python main.py --update-data
    python main.py --data-dir my_data --output my_output/report.html
    python main.py --help

Exit codes
----------
    0  全部階段成功完成
    1  任何錯誤（檔案不存在、欄位缺失、輸出失敗等）
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI 參數解析
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="分析台灣飛日本的票價、匯率與旅遊舒適度，產生靜態 HTML Dashboard。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        metavar="DATA_DIR",
        help="CSV 資料目錄（fares.csv / exchange_rates.csv / comfort_scores.csv）",
    )
    parser.add_argument(
        "--output",
        default="output/index.html",
        metavar="OUTPUT",
        help="HTML Dashboard 輸出路徑",
    )
    parser.add_argument(
        "--update-data",
        action="store_true",
        help=(
            "自動抓取上一個完整年度的匯率與氣候資料，"
            "覆蓋 exchange_rates.csv 與 comfort_scores.csv，"
            "然後執行分析並輸出 Dashboard。"
            "（fares.csv 不會被覆蓋，請手動更新）"
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 進度輸出輔助
# ---------------------------------------------------------------------------

def _done(stage: str) -> None:
    print(f"[INFO] {stage}")


def _error(reason: str) -> None:
    print(f"[ERROR] {reason}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[INFO] {msg}")


# ---------------------------------------------------------------------------
# 資料更新流程
# ---------------------------------------------------------------------------

def _get_last_complete_year() -> int:
    """
    自動判斷上一個完整年度。

    例如：目前是 2026 年 → 回傳 2025
          目前是 2027 年 → 回傳 2026
    """
    return date.today().year - 1


def run_update_data(data_dir: Path) -> bool:
    """
    執行資料更新流程：
    1. 自動判斷上一個完整年度
    2. 抓取匯率資料（臺灣銀行）→ 覆蓋 exchange_rates.csv
    3. 抓取氣候資料（JMA）→ 覆蓋 comfort_scores.csv
    4. 不覆蓋 fares.csv

    Parameters
    ----------
    data_dir : Path
        資料目錄路徑。

    Returns
    -------
    bool
        True = 更新成功（或部分成功，可繼續分析）
        False = 更新失敗且無既有 CSV 可用（應停止程式）
    """
    target_year = _get_last_complete_year()
    _info(f"Target year: {target_year} (current year: {date.today().year})")

    try:
        from src.fetcher import FetchError, fetch_exchange_rates, fetch_comfort_scores
    except ImportError as exc:
        _error(f"fetcher module import failed: {exc}")
        return _check_existing_csvs(data_dir)

    # ------------------------------------------------------------------
    # 更新匯率資料
    # ------------------------------------------------------------------
    exchange_path = data_dir / "exchange_rates.csv"

    try:
        rate_df = fetch_exchange_rates(target_year)
        rate_df.to_csv(exchange_path, index=False, encoding="utf-8")
        _done(f"Exchange rates written: {len(rate_df)} records → {exchange_path}")
    except FetchError as exc:
        print(f"[WARNING] Exchange rate fetch failed: {exc}", file=sys.stderr)
        if exchange_path.exists():
            print(f"[WARNING] Using existing {exchange_path}", file=sys.stderr)
        else:
            _error(f"Exchange rate fetch failed and {exchange_path} does not exist — cannot continue")
            return False
    except Exception as exc:
        print(f"[WARNING] Unexpected error during exchange rate update: {exc}", file=sys.stderr)
        if not exchange_path.exists():
            _error(f"Exchange rate update failed and {exchange_path} does not exist — cannot continue")
            return False

    # ------------------------------------------------------------------
    # 更新氣候資料
    # ------------------------------------------------------------------
    comfort_path = data_dir / "comfort_scores.csv"
    _info(f"Fetching climate data from JMA ({target_year})...")
    _info("Cities: Tokyo, Osaka, Fukuoka, Sapporo, Okinawa (Naha)")

    try:
        comfort_df = fetch_comfort_scores(target_year)
        comfort_df.to_csv(comfort_path, index=False, encoding="utf-8")
        _done(f"Climate data written: {len(comfort_df)} records → {comfort_path}")
    except FetchError as exc:
        print(f"[WARNING] Climate data fetch failed: {exc}", file=sys.stderr)
        if comfort_path.exists():
            print(f"[WARNING] Using existing {comfort_path}", file=sys.stderr)
        else:
            _error(f"Climate data fetch failed and {comfort_path} does not exist — cannot continue")
            return False
    except Exception as exc:
        print(f"[WARNING] Unexpected error during climate data update: {exc}", file=sys.stderr)
        if not comfort_path.exists():
            _error(f"Climate data update failed and {comfort_path} does not exist — cannot continue")
            return False

    # 提醒使用者 fares.csv 需手動更新
    fares_path = data_dir / "fares.csv"
    if fares_path.exists():
        _info("fares.csv: manual update only — skipped (update manually as needed)")
    else:
        print(
            f"[WARNING] {fares_path} not found. "
            "Fare analysis will have no data. "
            "Please create fares.csv manually (see README.md for format).",
            file=sys.stderr,
        )

    return True


def _check_existing_csvs(data_dir: Path) -> bool:
    """
    檢查既有 CSV 是否存在，決定是否可繼續分析。
    當 fetcher 模組無法載入時使用。
    """
    required = ["exchange_rates.csv", "comfort_scores.csv"]
    missing = [f for f in required if not (data_dir / f).exists()]
    if missing:
        _error(f"以下必要 CSV 不存在：{missing}，無法繼續分析")
        return False
    return True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_path = Path(args.output)

    # ------------------------------------------------------------------
    # 0. 驗證 data 目錄存在
    # ------------------------------------------------------------------
    if not data_dir.exists():
        _error(f"資料目錄不存在：{data_dir.resolve()}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 延遲 import（避免在 --help 時載入 pandas/plotly）
    # ------------------------------------------------------------------
    try:
        from src.analyzer import (
            analyze_comfort,
            analyze_exchange_rates,
            analyze_fares,
            fare_summary,
            rate_summary,
        )
        from src.data_loader import (
            load_comfort_scores,
            load_exchange_rates,
            load_fares,
        )
        from src.scorer import calculate_tci_all_cities
    except ImportError as exc:
        _error(f"模組載入失敗，請確認已安裝依賴（pip install -r requirements.txt）：{exc}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # --update-data：自動抓取上一個完整年度資料
    # ------------------------------------------------------------------
    if args.update_data:
        _info("Starting data update pipeline...")
        success = run_update_data(data_dir)
        if not success:
            sys.exit(1)
        print()  # 空行分隔更新流程與分析流程

    # ------------------------------------------------------------------
    # 1. 載入資料
    # ------------------------------------------------------------------
    _info("Running analysis...")
    try:
        fare_records = load_fares(data_dir / "fares.csv")
        rate_records = load_exchange_rates(data_dir / "exchange_rates.csv")
        comfort_records = load_comfort_scores(data_dir / "comfort_scores.csv")
    except SystemExit:
        raise
    except Exception as exc:
        _error(f"Data load failed: {exc}")
        sys.exit(1)

    _done("Data loaded")

    # ------------------------------------------------------------------
    # 2. 資料驗證摘要
    # ------------------------------------------------------------------
    _done("Data validated")

    # ------------------------------------------------------------------
    # 3. 票價分析
    # ------------------------------------------------------------------
    try:
        fare_result = analyze_fares(fare_records)
    except Exception as exc:
        _error(f"Fare analysis failed: {exc}")
        sys.exit(1)

    fs = fare_summary(fare_result)
    if fs["cheapest_month"]:
        print(
            f"       Cheapest month: {fs['cheapest_month']} "
            f"(TWD {fs['cheapest_fare']:,})  "
            f"Priciest: {fs['priciest_month']} "
            f"(TWD {fs['priciest_fare']:,})"
        )
    _done("Fare analysis complete")

    # ------------------------------------------------------------------
    # 4. 匯率分析
    # ------------------------------------------------------------------
    try:
        rate_result = analyze_exchange_rates(rate_records)
    except Exception as exc:
        _error(f"Exchange rate analysis failed: {exc}")
        sys.exit(1)

    rs = rate_summary(rate_result)
    if rs["best_months"]:
        months_str = ", ".join(f"{m}" for m in rs["best_months"])
        print(f"       Best exchange month(s): {months_str} (annual avg {rs['annual_avg']:.4f})")
    _done("Exchange rate analysis complete")

    # ------------------------------------------------------------------
    # 5. 舒適度分析
    # ------------------------------------------------------------------
    try:
        comfort_result = analyze_comfort(comfort_records)
    except Exception as exc:
        _error(f"Comfort analysis failed: {exc}")
        sys.exit(1)

    _done("Comfort analysis complete")

    # ------------------------------------------------------------------
    # 6. 綜合評分（TCI）
    # ------------------------------------------------------------------
    try:
        city_scores = calculate_tci_all_cities(fare_records, rate_result, comfort_result)
    except Exception as exc:
        _error(f"TCI calculation failed: {exc}")
        sys.exit(1)

    for city, score_result in city_scores.items():
        valid_scores = score_result.total_score.dropna()
        if not valid_scores.empty:
            best_month = int(valid_scores.idxmax())
            best_score = float(valid_scores.max())
            print(f"       {city}: best month = {best_month} (TCI {best_score})")
    _done("TCI scoring complete")

    # ------------------------------------------------------------------
    # 7. Dashboard 輸出
    # ------------------------------------------------------------------
    try:
        from src.renderer import render_dashboard
        render_dashboard(
            fare_result=fare_result,
            rate_result=rate_result,
            comfort_result=comfort_result,
            city_scores=city_scores,
            output_path=output_path,
            fare_records=fare_records,
        )
    except ImportError:
        _render_placeholder(output_path)
    except Exception as exc:
        _error(f"Dashboard render failed: {exc}")
        sys.exit(1)

    _done(f"Dashboard generated → {output_path.resolve()}")


# ---------------------------------------------------------------------------
# Renderer 佔位函式（Task 7 完成後由 src/renderer.py 取代）
# ---------------------------------------------------------------------------

def _render_placeholder(output_path: Path) -> None:
    """
    在 src/renderer.py 實作完成前，輸出一個簡單的 HTML 佔位頁面。
    確保 main.py 可以端對端執行。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>日本旅遊最佳出發時機分析</title>
  <style>
    body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; }}
    h1 {{ color: #d62728; }}
    .notice {{ background: #fff3cd; border: 1px solid #ffc107; padding: 16px; border-radius: 6px; }}
  </style>
</head>
<body>
  <header>
    <h1>日本旅遊最佳出發時機分析</h1>
    <p>資料更新日期：{date.today().isoformat()}</p>
  </header>
  <main>
    <div class="notice">
      <strong>⚠️ Dashboard 圖表尚未產生</strong><br>
      src/renderer.py（Task 7）完成後，此頁面將顯示完整的互動式分析圖表。
    </div>
  </main>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"輸出路徑：{output_path.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
