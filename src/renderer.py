
"""
src/renderer.py — 目的地分頁模式 Dashboard
"""
from __future__ import annotations
import sys
from datetime import date
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .models import ComfortAnalysisResult, FareAnalysisResult, RateAnalysisResult, ScoreResult

_MONTH_LABELS = [f"{m}月" for m in range(1, 13)]
_MONTHS = list(range(1, 13))
_AIRLINE_COLORS = {"CI": "#4C9BE8", "BR": "#2ECC71", "JX": "#E67E22"}
_DARK_BG = "#1a1a2e"
_CARD_BG = "#16213e"
_ACCENT = "#e94560"
_TEXT = "#eaeaea"
_SUBTEXT = "#a0a0b0"
_CITY_EMOJI = {"東京": "🗼", "大阪": "🏯", "福岡": "🌸", "札幌": "❄️", "沖繩": "🌺"}

def _tci_color(score: float) -> str:
    if score >= 80: return "#2ecc71"
    elif score >= 60: return "#f39c12"
    else: return "#e74c3c"

def _base_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=16, color=_TEXT), x=0.02),
        template="plotly_dark",
        paper_bgcolor=_CARD_BG,
        plot_bgcolor=_CARD_BG,
        font=dict(family="'Noto Sans TC','Microsoft JhengHei',sans-serif", color=_TEXT, size=11),
        margin=dict(l=55, r=25, t=55, b=45),
        height=400,
        autosize=True,
    )

def _fig_to_html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"responsive": True, "displayModeBar": False},
    )

def _series_to_js_array(s: "pd.Series") -> str:
    """將 pd.Series (index=1–12) 轉為 12 元素的 JS 陣列字串，NaN → null。"""
    vals = []
    for m in range(1, 13):
        v = s.get(m)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            vals.append("null")
        else:
            vals.append(f"{float(v):.4f}")
    return "[" + ", ".join(vals) + "]"


def _bool_series_to_js_array(s: "pd.Series") -> str:
    """將 bool pd.Series (index=1–12) 轉為 12 元素的 JS 陣列字串。"""
    vals = []
    for m in range(1, 13):
        v = s.get(m, False)
        vals.append("true" if bool(v) else "false")
    return "[" + ", ".join(vals) + "]"


def _build_weight_panel(tab_idx: int) -> str:
    """產生可折疊的權重調整面板 HTML。"""
    return f"""
<div class="weight-panel" id="weight-panel-{tab_idx}">
  <div class="weight-panel-header" onclick="toggleWeightPanel({tab_idx})">
    <span class="weight-panel-title">⚖️ 權重調整</span>
    <span class="weight-summary" id="weight-summary-{tab_idx}">
      TCI：舒適 50% ／ 票價 40% ／ 匯率 10%　｜　舒適：氣溫 40% ／ 降雨 30% ／ 人潮 30%
    </span>
    <button class="weight-toggle-btn" id="weight-toggle-btn-{tab_idx}" aria-expanded="false" aria-controls="weight-body-{tab_idx}">
      展開 ▼
    </button>
  </div>
  <div class="weight-panel-body" id="weight-body-{tab_idx}" style="display:none">
    <div class="weight-groups">
      <div class="weight-group">
        <div class="weight-group-title">TCI 權重</div>
        <div class="slider-row">
          <label>舒適度</label>
          <input type="range" min="0" max="100" value="50" class="weight-slider"
            id="w-comfort-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-comfort-{tab_idx}"><span class="slider-num">50</span> <span class="slider-pct">(50%)</span></span>
        </div>
        <div class="slider-row">
          <label>票價</label>
          <input type="range" min="0" max="100" value="40" class="weight-slider"
            id="w-fare-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-fare-{tab_idx}"><span class="slider-num">40</span> <span class="slider-pct">(40%)</span></span>
        </div>
        <div class="slider-row">
          <label>匯率</label>
          <input type="range" min="0" max="100" value="10" class="weight-slider"
            id="w-rate-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-rate-{tab_idx}"><span class="slider-num">10</span> <span class="slider-pct">(10%)</span></span>
        </div>
      </div>
      <div class="weight-group">
        <div class="weight-group-title">舒適度子權重</div>
        <div class="slider-row">
          <label>氣溫</label>
          <input type="range" min="0" max="100" value="40" class="weight-slider"
            id="w-temp-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-temp-{tab_idx}"><span class="slider-num">40</span> <span class="slider-pct">(40%)</span></span>
        </div>
        <div class="slider-row">
          <label>降雨</label>
          <input type="range" min="0" max="100" value="30" class="weight-slider"
            id="w-rain-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-rain-{tab_idx}"><span class="slider-num">30</span> <span class="slider-pct">(30%)</span></span>
        </div>
        <div class="slider-row">
          <label>人潮</label>
          <input type="range" min="0" max="100" value="30" class="weight-slider"
            id="w-crowd-{tab_idx}" oninput="onWeightChange({tab_idx})">
          <span class="slider-val" id="wv-crowd-{tab_idx}"><span class="slider-num">30</span> <span class="slider-pct">(30%)</span></span>
        </div>
      </div>
    </div>
    <div class="weight-actions">
      <button class="reset-btn" onclick="resetWeights({tab_idx})">↺ 重設為預設權重</button>
    </div>
  </div>
</div>"""


def _build_tci_chart(score_result: ScoreResult, city: str) -> go.Figure:
    tci = score_result.total_score.reindex(_MONTHS)
    fare = score_result.fare_score.reindex(_MONTHS)
    estimated = score_result.fare_estimated.reindex(_MONTHS).fillna(False)
    colors, texts = [], []
    for m in _MONTHS:
        val = tci.get(m)
        fare_val = fare.get(m)
        is_est = bool(estimated.get(m, False))
        if pd.isna(val):
            colors.append("#555566"); texts.append("無資料")
        elif is_est:
            colors.append(_tci_color(float(val))); texts.append(f"{val:.1f}~")
        elif pd.isna(fare_val):
            colors.append(_tci_color(float(val))); texts.append(f"{val:.1f}*")
        else:
            colors.append(_tci_color(float(val))); texts.append(f"{val:.1f}")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=_MONTH_LABELS,
        y=[float(v) if not pd.isna(v) else 0 for v in tci],
        marker_color=colors, text=texts, textposition="outside",
        textfont=dict(size=11, color=_TEXT),
        hovertemplate="<b>%{x}</b><br>TCI：%{text}<extra></extra>", name="TCI",
    ))
    valid = tci.dropna()
    if not valid.empty:
        best_m = int(valid.idxmax()); best_v = float(valid.max())
        fig.add_annotation(x=_MONTH_LABELS[best_m-1], y=best_v+6,
            text=f"🏆 最佳：{best_m}月", showarrow=False,
            font=dict(size=12, color="#f1c40f"))
    fig.update_layout(**_base_layout(f"{city} 綜合旅遊指數（TCI）各月排名"),
        yaxis=dict(range=[0, 115], title="TCI 分數", gridcolor="#2a2a4a"),
        xaxis=dict(title="月份"))
    return fig

def _build_fare_chart(fare_result: FareAnalysisResult, city: str, fare_estimated: "pd.Series | None" = None) -> go.Figure:
    """
    票價圖表。使用 fare_result.monthly_avg_by_airline（已含估算補值）。
    fare_result.estimated_by_airline 標記哪些格是估算值（淡色 + tooltip 標示）。
    """
    # 確保 index 對齊：用 1–12 整數 list reindex，不依賴 index name
    raw_df = fare_result.monthly_avg_by_airline
    df = raw_df.reindex(list(range(1, 13)))

    est_raw = fare_result.estimated_by_airline
    est_df = est_raw.reindex(list(range(1, 13))) if est_raw is not None else None

    fig = go.Figure()
    for airline in ["CI", "BR", "JX"]:
        if airline not in df.columns:
            continue
        vals = df[airline]

        # 補值後應全部有值；若仍全 NaN 才跳過
        if not vals.notna().any():
            continue

        y_vals = [float(v) if not pd.isna(v) else None for v in vals]

        # 判斷每個月份是否為估算值
        if est_df is not None and airline in est_df.columns:
            est_flags = [
                bool(est_df.loc[m, airline])
                if (not pd.isna(vals.get(m, float("nan"))))
                else False
                for m in range(1, 13)
            ]
        else:
            est_flags = [False] * 12

        # 顏色：估算值用半透明（opacity 0.35），實際值用正常顏色
        actual_color = _AIRLINE_COLORS.get(airline, "#aaa")
        hex_c = actual_color.lstrip("#")
        r_c, g_c, b_c = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)

        marker_colors = []
        for v, is_est in zip(y_vals, est_flags):
            if v is None:
                marker_colors.append("rgba(0,0,0,0)")
            elif is_est:
                marker_colors.append(f"rgba({r_c},{g_c},{b_c},0.25)")
            else:
                marker_colors.append(actual_color)

        hover = []
        for i, (v, is_est) in enumerate(zip(y_vals, est_flags)):
            if v is None:
                hover.append(f"<b>{_MONTH_LABELS[i]}</b><br>{airline}：無資料")
            elif is_est:
                hover.append(
                    f"<b>{_MONTH_LABELS[i]}</b><br>{airline}：NT$ {int(v):,}"
                    f"<br><span style='color:#f39c12'>⚠ 估算票價</span>"
                )
            else:
                hover.append(f"<b>{_MONTH_LABELS[i]}</b><br>{airline}：NT$ {int(v):,}")

        fig.add_trace(go.Bar(
            name=airline,
            x=_MONTH_LABELS,
            y=y_vals,
            marker_color=marker_colors,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ))

    # 最低票價標注
    min_fare = fare_result.monthly_min_fare.reindex(list(range(1, 13)))
    for idx, m in enumerate(range(1, 13)):
        v = min_fare.get(m)
        if v is not None and not pd.isna(v):
            # 判斷該月最低票價是否來自估算格
            is_est_min = False
            if est_df is not None:
                for airline in ["CI", "BR", "JX"]:
                    if airline in est_df.columns and airline in df.columns:
                        av = df.loc[m, airline]
                        if not pd.isna(av) and abs(float(av) - float(v)) < 1:
                            if bool(est_df.loc[m, airline]):
                                is_est_min = True
                                break
            label = f"NT${int(v):,}{'*' if is_est_min else ''}"
            fig.add_annotation(
                x=_MONTH_LABELS[idx], y=float(v),
                text=label, showarrow=False, yshift=13,
                font=dict(size=8, color="#f39c12" if is_est_min else _SUBTEXT),
            )

    fig.update_layout(
        **_base_layout(f"各航空公司月均來回票價（飛往{city}）"),
        barmode="group",
        yaxis=dict(title="票價（NT$）", gridcolor="#2a2a4a", tickformat=",.0f", tickprefix="NT$"),
        xaxis=dict(title="月份"),
        legend=dict(title="航空公司", bgcolor="rgba(0,0,0,0)"),
    )
    return fig

def _build_rate_chart(rate_result: RateAnalysisResult) -> go.Figure:
    rates = rate_result.monthly_avg_rate.reindex(_MONTHS)
    annual_avg = rate_result.annual_avg_rate
    best_months = rate_result.best_months
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_MONTH_LABELS, y=[float(v) if not pd.isna(v) else None for v in rates],
        mode="lines+markers", line=dict(color="#4C9BE8", width=2.5),
        marker=dict(size=7, color="#4C9BE8"), connectgaps=False, name="月均匯率",
        hovertemplate="<b>%{x}</b><br>匯率：%{y:.4f}<extra></extra>"))
    if annual_avg > 0:
        fig.add_hline(y=annual_avg, line_dash="dash", line_color="#f39c12",
            annotation_text=f"全年均值 {annual_avg:.4f}", annotation_position="top right",
            annotation_font=dict(color="#f39c12", size=10))
    for m in best_months:
        v = rates.get(m)
        if not pd.isna(v):
            fig.add_trace(go.Scatter(
                x=[_MONTH_LABELS[m-1]], y=[float(v)], mode="markers",
                marker=dict(symbol="star", size=16, color="#f1c40f",
                            line=dict(color="#fff", width=1)),
                name=f"最佳換匯（{m}月）",
                hovertemplate=f"<b>{m}月</b><br>最佳換匯（匯率最低）：{float(v):.4f}<extra></extra>",
                showlegend=True))
    valid = rates.dropna()
    y_min = float(valid.min()) * 0.997 if not valid.empty else 0
    y_max = float(valid.max()) * 1.003 if not valid.empty else 1
    fig.update_layout(**_base_layout("JPY/TWD 月均匯率走勢（各城市共用）"),
        yaxis=dict(title="匯率（1 JPY = ? TWD）", range=[y_min, y_max],
                   gridcolor="#2a2a4a", tickformat=".4f"),
        xaxis=dict(title="月份"), legend=dict(bgcolor="rgba(0,0,0,0)"))
    return fig

def _build_comfort_chart(comfort_result: ComfortAnalysisResult, city: str) -> go.Figure:
    if comfort_result.monthly_comfort.empty:
        fig = go.Figure()
        fig.add_annotation(text="無舒適度資料", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=_SUBTEXT))
        fig.update_layout(**_base_layout(f"{city} 旅遊舒適度分析"))
        return fig
    df = comfort_result.monthly_comfort.reset_index()
    city_df = df[df["city"] == city]
    if city_df.empty:
        fig = go.Figure()
        fig.add_annotation(text=f"無 {city} 舒適度資料", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=_SUBTEXT))
        fig.update_layout(**_base_layout(f"{city} 旅遊舒適度分析"))
        return fig
    monthly = city_df.groupby("month").agg(
        avg_rain=("rain_probability_pct", "mean"),
        avg_crowd=("crowd_index", "mean"),
        avg_temp=("avg_temp_c", "mean"),
    ).reindex(_MONTHS)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=_MONTH_LABELS, y=[float(v) if not pd.isna(v) else None for v in monthly["avg_rain"]],
        name="降雨機率（%）", marker_color="rgba(76,155,232,0.6)",
        hovertemplate="<b>%{x}</b><br>降雨機率：%{y:.0f}%<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=_MONTH_LABELS, y=[float(v) if not pd.isna(v) else None for v in monthly["avg_crowd"]],
        name="人潮指數（1–10）", mode="lines+markers",
        line=dict(color=_ACCENT, width=2.5), marker=dict(size=8, color=_ACCENT),
        connectgaps=False,
        hovertemplate="<b>%{x}</b><br>人潮指數：%{y:.1f}<extra></extra>"), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=_MONTH_LABELS, y=[float(v) if not pd.isna(v) else None for v in monthly["avg_temp"]],
        name="平均氣溫（°C）", mode="lines+markers",
        line=dict(color="#f39c12", width=2, dash="dot"), marker=dict(size=6, color="#f39c12"),
        connectgaps=False,
        hovertemplate="<b>%{x}</b><br>平均氣溫：%{y:.1f}°C<extra></extra>"), secondary_y=True)
    fig.update_layout(**_base_layout(f"{city} 旅遊舒適度（降雨 / 人潮 / 氣溫）"),
        legend=dict(bgcolor="rgba(0,0,0,0)"), barmode="overlay")
    fig.update_yaxes(title_text="降雨機率（%）", range=[0, 110],
                     gridcolor="#2a2a4a", secondary_y=False)
    fig.update_yaxes(title_text="人潮指數 / 氣溫", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="月份")
    return fig

def _build_tci_table_rows(score_result: ScoreResult) -> str:
    """產生 TCI 表格的 <tbody> 內容（不含 <table> 外框），供初始渲染與 JS 動態更新共用。"""
    tci = score_result.total_score.reindex(_MONTHS)
    fare = score_result.fare_score.reindex(_MONTHS)
    rate = score_result.rate_score.reindex(_MONTHS)
    comfort = score_result.comfort_score.reindex(_MONTHS)
    estimated = score_result.fare_estimated.reindex(_MONTHS).fillna(False)

    rows_data = sorted(
        [(m, tci.get(m)) for m in _MONTHS],
        key=lambda x: (pd.isna(x[1]), -(x[1] if not pd.isna(x[1]) else 0))
    )
    rows_html = ""
    for rank, (m, t) in enumerate(rows_data, 1):
        f_val, r_val, c_val = fare.get(m), rate.get(m), comfort.get(m)
        is_est = bool(estimated.get(m, False))

        if pd.isna(t):
            tci_cell = '<span style="color:#666">無資料</span>'; row_class = "row-na"
        else:
            color = _tci_color(float(t))
            tci_cell = f'<span style="color:{color};font-weight:bold">{t:.1f}</span>'
            row_class = "row-data"

        def _fmt(v, mark_est: bool = False) -> str:
            if pd.isna(v):
                return "—"
            s = f"{float(v):.1f}"
            if mark_est:
                s += ' <span style="color:#f39c12;font-size:0.72em" title="估算票價（跨城市平均）">估算</span>'
            return s

        medal = " 🥇" if rank == 1 and not pd.isna(t) else \
                " 🥈" if rank == 2 and not pd.isna(t) else \
                " 🥉" if rank == 3 and not pd.isna(t) else ""

        rows_html += f"""
        <tr class="{row_class}">
          <td>{rank}</td><td><strong>{m}月</strong>{medal}</td>
          <td>{tci_cell}</td>
          <td>{_fmt(c_val)}</td>
          <td>{_fmt(f_val, mark_est=is_est)}</td>
          <td>{_fmt(r_val)}</td>
        </tr>"""

    return rows_html


def _build_tci_table(score_result: ScoreResult) -> str:
    rows_html = _build_tci_table_rows(score_result)
    return f"""
    <table class="tci-table">
      <thead><tr>
        <th>排名</th><th>月份</th><th>TCI 總分</th>
        <th>舒適分 (50%)</th><th>票價分 (40%)</th><th>匯率分 (10%)</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""


def _build_city_tab_content(
    city: str,
    score_result: ScoreResult,
    fare_result: FareAnalysisResult,
    rate_result: RateAnalysisResult,
    comfort_result: ComfortAnalysisResult,
    tab_idx: int,
    fare_records: "list | None" = None,
) -> str:
    """產生單一城市分頁的完整 HTML 內容。"""
    emoji = _CITY_EMOJI.get(city, "📍")

    tci_fig = _build_tci_chart(score_result, city)

    # 票價圖表：使用補值後的完整資料（每月每航空公司都有值）
    if fare_records is not None:
        from .analyzer import build_fare_chart_data_for_city
        chart_fare_result = build_fare_chart_data_for_city(fare_records, city)
    else:
        chart_fare_result = fare_result
    fare_fig = _build_fare_chart(chart_fare_result, city)

    rate_fig = _build_rate_chart(rate_result)
    comfort_fig = _build_comfort_chart(comfort_result, city)

    tci_div = _fig_to_html(tci_fig, f"chart-tci-{tab_idx}")
    fare_div = _fig_to_html(fare_fig, f"chart-fare-{tab_idx}")
    rate_div = _fig_to_html(rate_fig, f"chart-rate-{tab_idx}")
    comfort_div = _fig_to_html(comfort_fig, f"chart-comfort-{tab_idx}")
    tci_table = _build_tci_table(score_result)

    valid_tci = score_result.total_score.dropna()
    if not valid_tci.empty:
        best_m = int(valid_tci.idxmax()); best_v = float(valid_tci.max())
        hero = f"最佳出發月份：<span class='hero-month'>{best_m} 月</span>（TCI {best_v:.1f} 分）"
    else:
        hero = "資料不足，無法計算最佳月份"

    # --- 嵌入子分數 JSON 供前端 JS 使用 ---
    fare_score_js   = _series_to_js_array(score_result.fare_score)
    rate_score_js   = _series_to_js_array(score_result.rate_score)
    comfort_score_js = _series_to_js_array(score_result.comfort_score)
    tci_score_js    = _series_to_js_array(score_result.total_score)
    estimated_js    = _bool_series_to_js_array(score_result.fare_estimated)

    # 舒適度子分數
    temp_s  = score_result.temp_score
    rain_s  = score_result.rain_score
    crowd_s = score_result.crowd_score
    temp_score_js  = _series_to_js_array(temp_s)  if temp_s  is not None else "[null,null,null,null,null,null,null,null,null,null,null,null]"
    rain_score_js  = _series_to_js_array(rain_s)  if rain_s  is not None else "[null,null,null,null,null,null,null,null,null,null,null,null]"
    crowd_score_js = _series_to_js_array(crowd_s) if crowd_s is not None else "[null,null,null,null,null,null,null,null,null,null,null,null]"

    weight_panel = _build_weight_panel(tab_idx)

    return f"""
<div class="tab-panel" id="panel-{tab_idx}">

  <script>
  (function() {{
    var _d = window._cityData = window._cityData || {{}};
    _d[{tab_idx}] = {{
      fareScore:    {fare_score_js},
      rateScore:    {rate_score_js},
      comfortScore: {comfort_score_js},
      tciScore:     {tci_score_js},
      estimated:    {estimated_js},
      tempScore:    {temp_score_js},
      rainScore:    {rain_score_js},
      crowdScore:   {crowd_score_js},
      chartTciId:   "chart-tci-{tab_idx}",
      tableId:      "tci-table-body-{tab_idx}",
      heroId:       "city-hero-text-{tab_idx}",
      descId:       "tci-desc-{tab_idx}"
    }};
  }})();
  </script>

  <div class="city-hero" id="city-hero-{tab_idx}">
    {emoji} {city}｜<span id="city-hero-text-{tab_idx}">{hero}</span>
  </div>

  {weight_panel}

  <section>
    <h2>📊 {city} 綜合旅遊指數（TCI）排名</h2>
    <p class="desc" id="tci-desc-{tab_idx}">TCI = 舒適度分數（<span class="desc-comfort-pct">50%</span>）＋ 票價分數（<span class="desc-fare-pct">40%</span>）＋ 匯率分數（<span class="desc-rate-pct">10%</span>）。<br>
      標示 <strong>~</strong> 的月份票價為<span style="color:#f39c12">估算票價</span>（以同月份其他目的地平均補值）；
      標示 <strong>*</strong> 的月份無票價資料，TCI 分數區間：
      <span style="color:#2ecc71">■</span> ≥80 優秀 &nbsp;
      <span style="color:#f39c12">■</span> 60–79 普通 &nbsp;
      <span style="color:#e74c3c">■</span> &lt;60 較差</p>
    <div class="chart-wrap">{tci_div}</div>
    <table class="tci-table">
      <thead><tr>
        <th>排名</th><th>月份</th>
        <th>TCI 總分</th>
        <th id="th-comfort-{tab_idx}">舒適分 (50%)</th>
        <th id="th-fare-{tab_idx}">票價分 (40%)</th>
        <th id="th-rate-{tab_idx}">匯率分 (10%)</th>
      </tr></thead>
      <tbody id="tci-table-body-{tab_idx}">{_build_tci_table_rows(score_result)}</tbody>
    </table>
  </section>

  <section>
    <h2>🌤️ {city} 旅遊舒適度分析</h2>
    <p class="desc" id="comfort-desc-{tab_idx}">
      藍色長條為降雨機率（%），紅色折線為人潮指數（1–10），橙色虛線為平均氣溫（°C）。<br>
      舒適度分數 = 氣溫（<span class="desc-temp-pct">40%</span>）+ 降雨（<span class="desc-rain-pct">30%</span>）+ 人潮（<span class="desc-crowd-pct">30%</span>）。<br>
      氣溫：採非線性舒適度曲線（非線性懲罰），18–22°C 為最佳舒適區間，過冷與過熱皆會快速降低舒適度分數。<br>
      降雨：降雨機率越高，舒適度越低。<br>
      人潮：依人潮指數評估壅擠程度，人潮越高舒適度越低，並採分段非線性方式加重高人潮月份的扣分。
    </p>
    <div class="chart-wrap">{comfort_div}</div>
  </section>

  <section>
    <h2>✈️ 飛往{city}的月均來回票價</h2>
    <p class="desc">依各航空公司分組計算月均來回票價（NT$）。長條頂端標示為該月最低票價。<br>
      <span style="color:{_SUBTEXT}">亮色柱狀為實際票價；<span style="color:#f39c12">深色柱狀</span>為估算票價（以同月份同航空公司其他目的地平均補值）。
      估算票價 tooltip 顯示「<span style="color:#f39c12">⚠ 估算票價</span>」，最低票價標示 <strong>*</strong>。</span></p>
    <div class="chart-wrap">{fare_div}</div>
    <div class="legend-row">
      <span><span class="legend-dot" style="background:#4C9BE8"></span>CI 中華航空</span>
      <span><span class="legend-dot" style="background:#2ECC71"></span>BR 長榮航空</span>
      <span><span class="legend-dot" style="background:#E67E22"></span>JX 星宇航空</span>
      <span>（亮色=實際，深色=估算）<span>
    </div>
  </section>

  <section>
    <h2>💱 JPY/TWD 月均匯率走勢</h2>
    <p class="desc">匯率不分城市，各分頁共用相同資料。
      ⭐ 星形標記為最佳換匯月份（匯率最低點）。</p>
    <div class="chart-wrap">{rate_div}</div>
  </section>
</div>"""


def render_dashboard(
    fare_result: FareAnalysisResult,
    rate_result: RateAnalysisResult,
    comfort_result: ComfortAnalysisResult,
    city_scores: dict[str, ScoreResult],
    output_path: str | Path = "output/index.html",
    fare_records: "list | None" = None,
) -> None:
    """
    產生目的地分頁模式的靜態 HTML Dashboard 並寫入檔案。

    Parameters
    ----------
    fare_result : FareAnalysisResult
        全域票價分析結果（備用，當 fare_records 未提供時使用）。
    rate_result : RateAnalysisResult
    comfort_result : ComfortAnalysisResult
    city_scores : dict[str, ScoreResult]
        {城市名稱: ScoreResult}，由 calculate_tci_all_cities() 產生。
    output_path : str | Path
    fare_records : list[FareRecord] | None
        原始票價記錄，用於依城市過濾票價圖表。若提供，每個城市顯示自己的票價。
    """
    output_path = Path(output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[錯誤] 無法建立輸出目錄 {output_path.parent}：{exc}", file=sys.stderr)
        raise

    cities = list(city_scores.keys())
    if not cities:
        cities = ["東京", "大阪", "福岡", "札幌", "沖繩"]

    # 強制 TAB 順序：東京、大阪、札幌、福岡、沖繩
    _PREFERRED_ORDER = ["東京", "大阪", "札幌", "福岡", "沖繩"]
    ordered = [c for c in _PREFERRED_ORDER if c in cities]
    remaining = [c for c in cities if c not in _PREFERRED_ORDER]
    cities = ordered + remaining

    tab_buttons = ""
    tab_panels = ""
    for i, city in enumerate(cities):
        emoji = _CITY_EMOJI.get(city, "📍")
        active_btn = " active" if i == 0 else ""
        tab_buttons += f'<button class="tab-btn{active_btn}" onclick="switchTab({i})" id="btn-{i}">{emoji} {city}</button>\n'
        score_result = city_scores.get(city)
        if score_result is None:
            tab_panels += f'<div class="tab-panel" id="panel-{i}"><p style="color:{_SUBTEXT};padding:40px">無 {city} 資料</p></div>\n'
        else:
            tab_panels += _build_city_tab_content(
                city, score_result, fare_result, rate_result, comfort_result, i,
                fare_records=fare_records,
            )

    from plotly.offline import get_plotlyjs
    plotly_js_inline = f"<script>{get_plotlyjs()}</script>"
    today = date.today().isoformat()

    html = _build_html_page(tab_buttons, tab_panels, plotly_js_inline, today)

    try:
        output_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"[錯誤] 無法寫入 {output_path}：{exc}", file=sys.stderr)
        raise

    print(f"輸出路徑：{output_path.resolve()}")


def _build_html_page(tab_buttons: str, tab_panels: str, plotly_js_inline: str, today: str) -> str:
    """組裝完整的 HTML 頁面字串。"""
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>日本旅遊最佳出發時機分析 Dashboard</title>
  {plotly_js_inline}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: {_DARK_BG};
      color: {_TEXT};
      font-family: 'Noto Sans TC','Microsoft JhengHei','PingFang TC',sans-serif;
      min-height: 100vh;
    }}
    header {{
      background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
      padding: 24px 40px 18px;
      border-bottom: 2px solid {_ACCENT};
    }}
    header h1 {{ font-size: 1.7rem; color: #fff; letter-spacing: 0.04em; }}
    header .meta {{ margin-top: 5px; font-size: 0.82rem; color: {_SUBTEXT}; }}

    /* Tab 切換列 */
    .tab-bar {{
      display: flex;
      gap: 4px;
      padding: 16px 40px 0;
      background: {_DARK_BG};
      border-bottom: 2px solid #2a2a4a;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: #16213e;
      color: {_SUBTEXT};
      border: 1px solid #2a2a4a;
      border-bottom: none;
      padding: 10px 22px;
      font-size: 0.95rem;
      font-family: inherit;
      cursor: pointer;
      border-radius: 6px 6px 0 0;
      transition: background 0.15s, color 0.15s;
    }}
    .tab-btn:hover {{ background: #1e2d50; color: {_TEXT}; }}
    .tab-btn.active {{
      background: {_CARD_BG};
      color: #fff;
      border-color: #3a3a6a;
      border-bottom: 1px solid #f39c12;
      margin-bottom: -2px;
      font-weight: 600;
      box-shadow: inset 0 -2px 0 #f39c12;
    }}

    /* 分頁內容 */
    .tab-panel {{ display: none; padding: 24px 40px 48px; }}
    .tab-panel.visible {{ display: block; }}

    .city-hero {{
      background: {_CARD_BG};
      border-left: 4px solid #f1c40f;
      margin-bottom: 24px;
      padding: 14px 22px;
      border-radius: 6px;
      font-size: 1.05rem;
    }}
    .hero-month {{ color: #f1c40f; font-size: 1.3rem; font-weight: bold; }}

    section {{
      background: {_CARD_BG};
      border-radius: 10px;
      padding: 18px 22px 14px;
      box-shadow: 0 4px 18px rgba(0,0,0,0.4);
      margin-bottom: 28px;
    }}
    section h2 {{
      font-size: 1.05rem; color: {_TEXT};
      padding-bottom: 9px; border-bottom: 1px solid #2a2a4a; margin-bottom: 4px;
    }}
    section p.desc {{
      font-size: 0.8rem; color: {_SUBTEXT};
      margin-bottom: 12px; line-height: 1.6;
    }}
    .chart-wrap {{
      width: 100%;
      overflow: visible;
      display: block;
    }}
    .chart-wrap > div {{
      width: 100% !important;
      min-width: 0 !important;
    }}
    .chart-wrap .plotly-graph-div {{
      width: 100% !important;
    }}

    .tci-table {{
      width: 100%; border-collapse: collapse;
      font-size: 0.88rem; margin-top: 14px;
    }}
    .tci-table th {{
      background: #0f3460; color: {_TEXT};
      padding: 9px 12px; text-align: center; font-weight: 600;
    }}
    .tci-table td {{
      padding: 8px 12px; text-align: center;
      border-bottom: 1px solid #2a2a4a;
    }}
    .tci-table tr.row-data:hover td {{ background: rgba(255,255,255,0.04); }}
    .tci-table tr.row-na td {{ color: #666; }}

    .legend-row {{
      display: flex; gap: 18px; flex-wrap: wrap;
      margin-top: 9px; font-size: 0.78rem; color: {_SUBTEXT};
    }}
    .legend-dot {{
      display: inline-block; width: 9px; height: 9px;
      border-radius: 50%; margin-right: 4px; vertical-align: middle;
    }}

    /* ── 權重調整面板 ── */
    .weight-panel {{
      background: #0f1e3a;
      border: 1px solid #2a3a5a;
      border-radius: 8px;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .weight-panel-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 11px 18px;
      cursor: pointer;
      user-select: none;
      flex-wrap: wrap;
    }}
    .weight-panel-header:hover {{ background: rgba(255,255,255,0.03); }}
    .weight-panel-title {{
      font-size: 0.95rem;
      font-weight: 600;
      color: {_TEXT};
      white-space: nowrap;
    }}
    .weight-summary {{
      flex: 1;
      font-size: 0.78rem;
      color: {_SUBTEXT};
      min-width: 0;
    }}
    .weight-toggle-btn {{
      background: #1e3060;
      color: {_TEXT};
      border: 1px solid #3a4a7a;
      border-radius: 4px;
      padding: 4px 12px;
      font-size: 0.78rem;
      font-family: inherit;
      cursor: pointer;
      white-space: nowrap;
      transition: background 0.15s;
    }}
    .weight-toggle-btn:hover {{ background: #2a4080; }}
    .weight-panel-body {{
      padding: 16px 18px 14px;
      border-top: 1px solid #2a3a5a;
    }}
    .weight-groups {{
      display: flex;
      gap: 32px;
      flex-wrap: wrap;
    }}
    .weight-group {{
      flex: 1;
      min-width: 220px;
    }}
    .weight-group-title {{
      font-size: 0.82rem;
      font-weight: 600;
      color: #a0b0d0;
      margin-bottom: 10px;
      padding-bottom: 5px;
      border-bottom: 1px solid #2a3a5a;
    }}
    .slider-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 9px;
    }}
    .slider-row label {{
      width: 52px;
      font-size: 0.82rem;
      color: {_SUBTEXT};
      flex-shrink: 0;
    }}
    .weight-slider {{
      flex: 1;
      -webkit-appearance: none;
      appearance: none;
      height: 5px;
      border-radius: 3px;
      background: #2a3a5a;
      outline: none;
      cursor: pointer;
    }}
    .weight-slider::-webkit-slider-thumb {{
      -webkit-appearance: none;
      appearance: none;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #56adff;
      cursor: pointer;
      box-shadow: 0 0 6px rgba(76,155,232,0.6);
    }}
    .weight-slider::-moz-range-thumb {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #56adff;
      cursor: pointer;
      box-shadow: 0 0 6px rgba(76,155,232,0.6);
    }}
    .slider-val {{
      width: 100px;
      text-align: right;
      font-size: 0.82rem;
      font-weight: 500;
      flex-shrink: 0;
      white-space: nowrap;
    }}
    .slider-num {{
      color: #6bb8ff;
      font-weight: 600;
    }}
    .slider-pct {{
      color: #a0a0b0;
      margin-left: 5px;
      font-weight: 500;
    }}
    .weight-actions {{
      margin-top: 14px;
      display: flex;
      justify-content: flex-end;
    }}
    .reset-btn {{
      background: #1e3060;
      color: {_TEXT};
      border: 1px solid #3a4a7a;
      border-radius: 5px;
      padding: 6px 16px;
      font-size: 0.82rem;
      font-family: inherit;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .reset-btn:hover {{ background: #2a4080; }}

    @media (max-width: 768px) {{
      header, .tab-bar, .tab-panel {{ padding-left: 14px; padding-right: 14px; }}
      header h1 {{ font-size: 1.2rem; }}
      .tab-btn {{ padding: 8px 14px; font-size: 0.85rem; }}
      .weight-groups {{ flex-direction: column; gap: 16px; }}
    }}
  </style>
</head>
<body>

<header>
  <h1>🗾 日本旅遊最佳出發時機分析 Dashboard</h1>
  <p class="meta">資料更新日期：{today} ｜ 分析航空：中華航空（CI）、長榮航空（BR）、星宇航空（JX）｜ 目的地分頁模式</p>
</header>

<div class="tab-bar">
{tab_buttons}
</div>

{tab_panels}

<script>
// ── Tab 切換 ──────────────────────────────────────────────────────────────
function switchTab(idx) {{
  document.querySelectorAll('.tab-panel').forEach(function(p, i) {{
    p.classList.toggle('visible', i === idx);
  }});
  document.querySelectorAll('.tab-btn').forEach(function(b, i) {{
    b.classList.toggle('active', i === idx);
  }});
  setTimeout(function() {{
    var panel = document.getElementById('panel-' + idx);
    if (panel) {{
      var divs = panel.querySelectorAll('.plotly-graph-div');
      divs.forEach(function(d) {{
        if (window.Plotly) {{ Plotly.relayout(d, {{autosize: true}}); }}
      }});
    }}
  }}, 50);
}}
switchTab(0);

// ── 權重調整面板 ──────────────────────────────────────────────────────────
function toggleWeightPanel(idx) {{
  var body = document.getElementById('weight-body-' + idx);
  var btn  = document.getElementById('weight-toggle-btn-' + idx);
  var open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  btn.textContent    = open ? '收合 \u25b2' : '\u5c55\u958b \u25bc';
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}}

// ── 正規化輔助 ────────────────────────────────────────────────────────────
function normalizeWeights(a, b, c) {{
  var sum = a + b + c;
  if (sum === 0) {{ return [1/3, 1/3, 1/3]; }}
  return [a/sum, b/sum, c/sum];
}}

function pct(v) {{ return Math.round(v * 100) + '%'; }}

// ── TCI 顏色 ──────────────────────────────────────────────────────────────
function tciColor(score) {{
  if (score >= 80) return '#2ecc71';
  if (score >= 60) return '#f39c12';
  return '#e74c3c';
}}

// ── 滑桿變更 → 重新計算 ──────────────────────────────────────────────────
function onWeightChange(idx) {{
  var d = window._cityData[idx];
  if (!d) return;

  var wComfort = +document.getElementById('w-comfort-' + idx).value;
  var wFare    = +document.getElementById('w-fare-'    + idx).value;
  var wRate    = +document.getElementById('w-rate-'    + idx).value;
  var wTemp    = +document.getElementById('w-temp-'    + idx).value;
  var wRain    = +document.getElementById('w-rain-'    + idx).value;
  var wCrowd   = +document.getElementById('w-crowd-'   + idx).value;

  var tciW     = normalizeWeights(wComfort, wFare, wRate);
  var comfortW = normalizeWeights(wTemp, wRain, wCrowd);

  document.getElementById('wv-comfort-' + idx).innerHTML = '<span class="slider-num">' + wComfort + '</span> <span class="slider-pct">(' + pct(tciW[0]) + ')</span>';
  document.getElementById('wv-fare-'    + idx).innerHTML = '<span class="slider-num">' + wFare    + '</span> <span class="slider-pct">(' + pct(tciW[1]) + ')</span>';
  document.getElementById('wv-rate-'    + idx).innerHTML = '<span class="slider-num">' + wRate    + '</span> <span class="slider-pct">(' + pct(tciW[2]) + ')</span>';
  document.getElementById('wv-temp-'    + idx).innerHTML = '<span class="slider-num">' + wTemp    + '</span> <span class="slider-pct">(' + pct(comfortW[0]) + ')</span>';
  document.getElementById('wv-rain-'    + idx).innerHTML = '<span class="slider-num">' + wRain    + '</span> <span class="slider-pct">(' + pct(comfortW[1]) + ')</span>';
  document.getElementById('wv-crowd-'   + idx).innerHTML = '<span class="slider-num">' + wCrowd   + '</span> <span class="slider-pct">(' + pct(comfortW[2]) + ')</span>';

  var summary = document.getElementById('weight-summary-' + idx);
  if (summary) {{
    summary.textContent =
      'TCI\uff1a\u8212\u9069 ' + pct(tciW[0]) + ' \uff0f \u7968\u50f9 ' + pct(tciW[1]) + ' \uff0f \u532f\u7387 ' + pct(tciW[2]) +
      '\u3000|\u3000\u8212\u9069\uff1a\u6c23\u6eab ' + pct(comfortW[0]) + ' \uff0f \u964d\u96e8 ' + pct(comfortW[1]) + ' \uff0f \u4eba\u6f6e ' + pct(comfortW[2]);
  }}

  var newComfort = [], newTci = [];
  for (var i = 0; i < 12; i++) {{
    var ts = d.tempScore[i], rs = d.rainScore[i], cs = d.crowdScore[i];
    var comfort;
    if (ts === null && rs === null && cs === null) {{
      comfort = null;
    }} else {{
      comfort = (ts !== null ? ts : 0) * comfortW[0]
              + (rs !== null ? rs : 0) * comfortW[1]
              + (cs !== null ? cs : 0) * comfortW[2];
      comfort = Math.min(100, Math.max(0, comfort));
    }}
    newComfort.push(comfort);

    var fare = d.fareScore[i], rate = d.rateScore[i];
    var tci;
    if (fare === null && rate === null && comfort === null) {{
      tci = null;
    }} else {{
      tci = (fare    !== null ? fare    : 0) * tciW[1]
          + (rate    !== null ? rate    : 0) * tciW[2]
          + (comfort !== null ? comfort : 0) * tciW[0];
      tci = Math.min(100, Math.max(0, tci));
      tci = Math.round(tci * 10) / 10;
    }}
    newTci.push(tci);
  }}

  // 更新 TCI 長條圖
  var chartDiv = document.getElementById(d.chartTciId);
  if (chartDiv && window.Plotly) {{
    var colors = [], texts = [];
    for (var i = 0; i < 12; i++) {{
      var val = newTci[i];
      var isEst = d.estimated[i];
      if (val === null) {{
        colors.push('#555566'); texts.push('\u7121\u8cc7\u6599');
      }} else if (isEst) {{
        colors.push(tciColor(val)); texts.push(val.toFixed(1) + '~');
      }} else {{
        colors.push(tciColor(val)); texts.push(val.toFixed(1));
      }}
    }}
    var yVals = newTci.map(function(v) {{ return v === null ? 0 : v; }});
    Plotly.restyle(chartDiv, {{
      'marker.color': [colors],
      'text': [texts],
      'y': [yVals]
    }}, [0]);

    var bestVal = null, bestIdx = -1;
    for (var i = 0; i < 12; i++) {{
      if (newTci[i] !== null && (bestVal === null || newTci[i] > bestVal)) {{
        bestVal = newTci[i]; bestIdx = i;
      }}
    }}
    var monthLabels = ['1\u6708','2\u6708','3\u6708','4\u6708','5\u6708','6\u6708','7\u6708','8\u6708','9\u6708','10\u6708','11\u6708','12\u6708'];
    var annotations = bestIdx >= 0 ? [{{
      x: monthLabels[bestIdx],
      y: bestVal + 6,
      text: '\U0001F3C6 \u6700\u4f73\uff1a' + (bestIdx+1) + '\u6708',
      showarrow: false,
      font: {{ size: 12, color: '#f1c40f' }}
    }}] : [];
    Plotly.relayout(chartDiv, {{ annotations: annotations }});
  }}

  // 更新 hero 文字
  var heroEl = document.getElementById(d.heroId);
  if (heroEl) {{
    var bestVal2 = null, bestIdx2 = -1;
    for (var i = 0; i < 12; i++) {{
      if (newTci[i] !== null && (bestVal2 === null || newTci[i] > bestVal2)) {{
        bestVal2 = newTci[i]; bestIdx2 = i;
      }}
    }}
    if (bestIdx2 >= 0) {{
      heroEl.innerHTML = '\u6700\u4f73\u51fa\u767c\u6708\u4efd\uff1a<span class="hero-month">' + (bestIdx2+1) + ' \u6708</span>\uff08TCI ' + bestVal2.toFixed(1) + ' \u5206\uff09';
    }} else {{
      heroEl.textContent = '\u8cc7\u6599\u4e0d\u8db3\uff0c\u7121\u6cd5\u8a08\u7b97\u6700\u4f73\u6708\u4efd';
    }}
  }}

  // 更新表格欄位標題
  var thComfort = document.getElementById('th-comfort-' + idx);
  var thFare    = document.getElementById('th-fare-'    + idx);
  var thRate    = document.getElementById('th-rate-'    + idx);
  if (thComfort) thComfort.textContent = '\u8212\u9069\u5206 (' + pct(tciW[0]) + ')';
  if (thFare)    thFare.textContent    = '\u7968\u50f9\u5206 (' + pct(tciW[1]) + ')';
  if (thRate)    thRate.textContent    = '\u532f\u7387\u5206 (' + pct(tciW[2]) + ')';

  // 更新 TCI 表格內容
  var tbody = document.getElementById(d.tableId);
  if (tbody) {{
    var rowData = [];
    for (var i = 0; i < 12; i++) {{
      rowData.push({{ month: i+1, tci: newTci[i], comfort: newComfort[i],
                      fare: d.fareScore[i], rate: d.rateScore[i], est: d.estimated[i] }});
    }}
    rowData.sort(function(a, b) {{
      if (a.tci === null && b.tci === null) return 0;
      if (a.tci === null) return 1;
      if (b.tci === null) return -1;
      return b.tci - a.tci;
    }});

    var medals = [' \U0001F947', ' \U0001F948', ' \U0001F949'];
    var html = '';
    for (var rank = 0; rank < rowData.length; rank++) {{
      var r = rowData[rank];
      var medal = rank < 3 && r.tci !== null ? medals[rank] : '';
      var tciCell, rowClass;
      if (r.tci === null) {{
        tciCell = '<span style="color:#666">\u7121\u8cc7\u6599</span>';
        rowClass = 'row-na';
      }} else {{
        var col = tciColor(r.tci);
        tciCell = '<span style="color:' + col + ';font-weight:bold">' + r.tci.toFixed(1) + '</span>';
        rowClass = 'row-data';
      }}
      function fmtCell(v, isEst) {{
        if (v === null) return '\u2014';
        var s = v.toFixed(1);
        if (isEst) s += ' <span style="color:#f39c12;font-size:0.72em" title="\u4f30\u7b97\u7968\u50f9\uff08\u8de8\u57ce\u5e02\u5e73\u5747\uff09">\u4f30\u7b97</span>';
        return s;
      }}
      html += '<tr class="' + rowClass + '">'
            + '<td>' + (rank+1) + '</td>'
            + '<td><strong>' + r.month + '\u6708</strong>' + medal + '</td>'
            + '<td>' + tciCell + '</td>'
            + '<td>' + fmtCell(r.comfort, false) + '</td>'
            + '<td>' + fmtCell(r.fare, r.est) + '</td>'
            + '<td>' + fmtCell(r.rate, false) + '</td>'
            + '</tr>';
    }}
    tbody.innerHTML = html;
  }}

  // 更新說明文字中的百分比
  var descEl = document.getElementById(d.descId);
  if (descEl) {{
    var cp = pct(tciW[0]), fp = pct(tciW[1]), rp = pct(tciW[2]);
    var spanC = descEl.querySelector('.desc-comfort-pct');
    var spanF = descEl.querySelector('.desc-fare-pct');
    var spanR = descEl.querySelector('.desc-rate-pct');
    if (spanC) spanC.textContent = cp;
    if (spanF) spanF.textContent = fp;
    if (spanR) spanR.textContent = rp;
  }}

  var comfortDescEl = document.getElementById('comfort-desc-' + idx);
  if (comfortDescEl) {{
    var tp = pct(comfortW[0]), rainp = pct(comfortW[1]), crowdp = pct(comfortW[2]);
    var spanT = comfortDescEl.querySelector('.desc-temp-pct');
    var spanRain = comfortDescEl.querySelector('.desc-rain-pct');
    var spanCrowd = comfortDescEl.querySelector('.desc-crowd-pct');
    if (spanT) spanT.textContent = tp;
    if (spanRain) spanRain.textContent = rainp;
    if (spanCrowd) spanCrowd.textContent = crowdp;
  }}
}}

// ── 重設為預設權重 ────────────────────────────────────────────────────────
function resetWeights(idx) {{
  document.getElementById('w-comfort-' + idx).value = 50;
  document.getElementById('w-fare-'    + idx).value = 40;
  document.getElementById('w-rate-'    + idx).value = 10;
  document.getElementById('w-temp-'    + idx).value = 40;
  document.getElementById('w-rain-'    + idx).value = 30;
  document.getElementById('w-crowd-'   + idx).value = 30;
  onWeightChange(idx);
}}
</script>

<footer style="
    text-align:center;
    color:#8a93a8;
    font-size:0.85rem;
    margin:48px 0 24px 0;
    letter-spacing:0.03em;
">
    Japan Travel Dashboard Project &#124; LzhLabo<br>
</footer>
</body>
</html>"""