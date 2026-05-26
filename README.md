# 日本旅遊最佳出發時機分析 Dashboard

分析台灣飛日本的來回票價（中華航空 CI、長榮航空 BR、星宇航空 JX）、JPY/TWD 匯率與旅遊舒適度，找出最划算且舒適的出國時機，並輸出單一可離線瀏覽的 HTML Dashboard。

> **本專案分析的是「上一個完整年度的最佳旅遊月份」，不是即時旅遊監測系統。**

---

## 專案展示

![Dashboard Full](assets/dashboard-full.png)

---

## 安裝

```bash
pip install -r requirements.txt
```

---

## 使用方式

```bash
# 使用現有 CSV 資料執行分析並產生 Dashboard
python main.py

# 自動抓取上一個完整年度資料，再執行分析
python main.py --update-data

# 指定自訂資料目錄與輸出路徑
python main.py --data-dir my_data --output my_output/report.html

# 查看說明
python main.py --help
```

---

## --update-data 說明

執行 `python main.py --update-data` 時，程式會：

1. **自動判斷上一個完整年度**
   - 目前是 2026 年 → 抓取 2025 年全年資料
   - 目前是 2027 年 → 抓取 2026 年全年資料
   - 不需要手動指定年份

2. **自動更新匯率資料**（覆蓋 `data/exchange_rates.csv`）
   - 資料來源：臺灣銀行歷史匯率
   - URL：https://rate.bot.com.tw/xrt/history?Lang=zh-TW
   - 抓取上一個完整年度的 JPY/TWD 每日即期賣出匯率

3. **自動更新氣候資料**（覆蓋 `data/comfort_scores.csv`）
   - 資料來源：日本氣象廳（JMA）歷史氣候資料
   - URL：https://www.data.jma.go.jp/stats/etrn/index.php
   - 抓取城市：東京、大阪、京都、福岡、札幌
   - 每月資料：月均氣溫（°C）、月降水量（mm，轉換為降雨機率 %）

4. **不覆蓋 `data/fares.csv`**
   - 機票資料目前為人工整理與手動更新，請依需求自行維護

5. **執行分析並輸出 Dashboard**

### 錯誤處理

- 若網站連線失敗或 HTML 結構變更，會顯示清楚的錯誤訊息
- 若既有 CSV 存在，允許使用既有資料繼續分析
- 若 CSV 不存在且抓取失敗，程式會停止並提示原因

---

## 資料說明

### crowd_index（旅遊熱度推估指標）

`crowd_index` 為旅遊旺季熱度推估指標，**不是即時人流監測資料**。

評分依據（1–10 分）：
- 櫻花季（4 月）
- 黃金週（5 月初）
- 暑假（7–8 月）
- 楓葉季（11 月）
- 年末年始（1 月初、12 月底）
- 日本國定假日與觀光旺季規律

### 機票資料（fares.csv）

機票資料目前為人工整理與手動更新。

本專案不提供機票爬蟲，也不串接 Google Flights、Skyscanner 或其他第三方 API。請依實際需求手動更新 `data/fares.csv`。

---

## 資料格式

### data/fares.csv（手動更新）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `date` | YYYY-MM-DD | 票價查詢日期 |
| `airline` | CI / BR / JX | 航空公司代碼 |
| `origin` | IATA 代碼 | 出發機場（例：TPE） |
| `destination` | 目的地城市名稱 | 例：東京、大阪、福岡、札幌、沖繩 |
| `roundtrip_fare_twd` | 正整數 | 來回票價（新台幣） |

```csv
date,airline,origin,destination,roundtrip_fare_twd
2025-01-05,CI,TPE,東京,15800
2025-01-12,BR,TPE,大阪,14200
2025-01-20,JX,TPE,東京,13500
```

### data/exchange_rates.csv（--update-data 自動更新）

資料來源：臺灣銀行歷史匯率

| 欄位 | 型別 | 說明 |
|------|------|------|
| `date` | YYYY-MM-DD | 匯率日期 |
| `jpy_twd_rate` | 正浮點數 | JPY/TWD 匯率（1 日圓 = ? 台幣） |

```csv
date,jpy_twd_rate
2025-01-01,0.2212
2025-01-02,0.2200
```

### data/comfort_scores.csv（--update-data 自動更新）

資料來源：日本氣象廳（JMA）歷史氣候資料 + 旅遊旺季熱度推估模型

| 欄位 | 型別 | 說明 |
|------|------|------|
| `year` | 整數 | 資料年度 |
| `month` | 1–12 | 月份 |
| `city` | 字串 | 目的地城市（東京、大阪、京都、福岡、札幌） |
| `avg_temp_c` | 浮點數 | 月均氣溫（°C） |
| `rain_probability_pct` | 0–100 整數 | 降雨機率（%，由月降水量 mm 轉換） |
| `crowd_index` | 1–10 整數 | 旅遊熱度推估指數（1=人少，10=非常擁擠） |

```csv
year,month,city,avg_temp_c,rain_probability_pct,crowd_index
2025,1,東京,6.1,20,6
2025,4,東京,15.2,35,9
```

---

## 專案結構

```
japan-travel-dashboard/
├── main.py              # CLI 入口（含 --update-data 流程）
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── models.py        # 資料模型（dataclass）
│   ├── data_loader.py   # CSV 讀取與驗證
│   ├── fetcher.py       # 自動資料抓取（匯率、氣候）
│   ├── analyzer.py      # 票價、匯率、舒適度分析
│   ├── scorer.py        # 綜合評分計算（TCI）
│   └── renderer.py      # plotly 圖表與 HTML 輸出
├── data/                # CSV 資料檔案
│   ├── fares.csv            # 航班來回票價（手動更新）
│   ├── exchange_rates.csv   # JPY/TWD 匯率（--update-data 自動更新）
│   └── comfort_scores.csv   # 旅遊舒適度（--update-data 自動更新）
├── output/              # 產生的 HTML Dashboard
├── assets/              # Dashboard 展示圖片
└── tests/               # pytest 單元測試
```

---

## 輸出

執行後會在 `output/index.html` 產生互動式 Dashboard，包含：

1. **綜合評分總覽** — 各月份綜合評分長條圖，標示最佳出發月份
2. **旅遊舒適度分析** — 人潮熱力圖與降雨機率長條圖
3. **票價分析** — 三家航空公司月均票價折線圖
4. **匯率分析** — JPY/TWD 月均匯率走勢，標示最佳換匯月份

HTML 檔案內嵌所有資源，可在無網路環境下開啟。

---

## 注意事項

- 本專案分析的是「上一個完整年度的最佳旅遊月份」，不是即時旅遊監測系統
- 匯率資料使用臺灣銀行歷史即期賣出匯率
- 氣候資料使用日本氣象廳（JMA）歷史月別統計
- crowd_index 為旅遊旺季熱度推估指標，不是即時人流監測資料
- 機票資料目前為手動更新 CSV，不提供自動抓取功能
