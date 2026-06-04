import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import requests
import re
import plotly.graph_objects as gr
from plotly.subplots import make_subplots

# 網頁基本設定
st.set_page_config(page_title="盤中即時三關價風控儀表板", page_icon="📈", layout="centered")

st.title("📈 盤中即時三關價 ＆ 出場風控雷達")
st.markdown("輸入台股**股票代號**或**中文名稱**，立刻獲取最新盤中價格、三關價防守位置與專業 KD K線圖。")

# ───【核心函數：將中文名稱自動精準轉換為數字代號】───
def convert_name_to_symbol(input_string):
    input_string = input_string.strip()
    if input_string.isdigit():
        return input_string
    try:
        search_url = f"https://query1.finance.yahoo.com/v1/finance/search?q={input_string}&lang=zh-Hant-TW&region=TW"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(search_url, headers=headers, timeout=3)
        if response.status_code == 200:
            result = response.json()
            quotes = result.get("quotes", [])
            for q in quotes:
                symbol = q.get("symbol", "")
                if symbol.endswith(".TW") or symbol.endswith(".TWO"):
                    return symbol.split(".")[0]
    except Exception:
        pass
    return None

# ───【核心函數：專門抓取台灣本土中文名稱】───
def get_taiwan_chinese_name(symbol):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            title_match = re.search(r'<title>(.*?)</title>', res.text)
            if title_match:
                title_text = title_match.group(1)
                chinese_name = title_text.split('(')[0].strip()
                if chinese_name and "Yahoo" not in chinese_name and "找不到" not in chinese_name:
                    return chinese_name
    except Exception:
        pass
    return ""

# 1. 介面輸入
user_input = st.text_input("🔍 請輸入股票代號或中文名稱（例如：2330、8908 或 台積電、欣雄）：", "2330").strip()

if user_input:
    with st.spinner(f"🚀 正在辨識並抓取【{user_input}】最新盤中數據與 KD 圖表..."):
        stock_input = convert_name_to_symbol(user_input)
        
        if not stock_input:
            st.error(f"❌ 找不到與「{user_input}」相符的台灣上市或上櫃股票。")
        else:
            try:
                # 為了計算準確的 9 天 KD 指標，抓取 3 個月資料比較穩健
                ticker_id = f"{stock_input}.TW"
                stock_data = yf.download(ticker_id, period="3mo", interval="1d", progress=False)
                
                if stock_data.empty or len(stock_data) < 9:
                    ticker_id = f"{stock_input}.TWO"
                    stock_data = yf.download(ticker_id, period="3mo", interval="1d", progress=False)
                
                if stock_data.empty or len(stock_data) < 9:
                    st.error("❌ 找不到該股票足夠的歷史數據。")
                else:
                    ticker = yf.Ticker(ticker_id)
                    df = stock_data.dropna().copy()
                    
                    if isinstance(df.columns, pd.MultiIndex):
                        for level in range(df.columns.nlevels):
                            labels = [str(c).lower() for c in df.columns.get_level_values(level)]
                            if 'close' in labels:
                                df.columns = df.columns.get_level_values(level)
                                break
                    df.columns = [str(c).lower() for c in df.columns]
                    
                    # ───【核心技術計算：三關價】───
                    df['prev_high'] = df['high'].shift(1)
                    df['prev_low'] = df['low'].shift(1)
                    df['上關壓力線'] = df['prev_low'] + (df['prev_high'] - df['prev_low']) * 1.382
                    df['中關分水嶺'] = (df['prev_high'] + df['prev_low']) / 2
                    df['下關支撐線'] = df['prev_high'] - (df['prev_high'] - df['prev_low']) * 1.382
                    
                    # ───【核心技術計算：標準常規 9-3-3 KD 指標】───
                    df['9h'] = df['high'].rolling(window=9).max()
                    df['9l'] = df['low'].rolling(window=9).min()
                    df['rsv'] = 50.0
                    non_zero = (df['9h'] - df['9l']) != 0
                    df.loc[non_zero, 'rsv'] = ((df['close'] - df['9l']) / (df['9h'] - df['9l'])) * 100
                    
                    k_list, d_list = [], []
                    current_k, current_d = 50.0, 50.0
                    for rsv_val in df['rsv']:
                        if pd.isna(rsv_val):
                            k_list.append(None)
                            d_list.append(None)
                        else:
                            current_k = (2/3) * current_k + (1/3) * rsv_val
                            current_d = (2/3) * current_d + (1/3) * current_k
                            k_list.append(current_k)
                            d_list.append(current_d)
                    df['K線'] = k_list
                    df['D線'] = d_list
                    # ──────────────────────────────────────────────
                    
                    # 提取當天最新數據
                    close_today = round(float(df['close'].iloc[-1]), 2)
                    high_today = round(float(df['high'].iloc[-1]), 2)
                    low_today = round(float(df['low'].iloc[-1]), 2)
                    open_today = round(float(df['open'].iloc[-1]), 2)
                    volume_today = int(df['volume'].iloc[-1] / 1000)
                    
                    p_upper = round(float(df['上關壓力線'].iloc[-1]), 2)
                    p_mid = round(float(df['中關分水嶺'].iloc[-1]), 2)
                    p_lower = round(float(df['下關支撐線'].iloc[-1]), 2)
                    
                    # 名稱處理
                    ch_name = get_taiwan_chinese_name(stock_input)
                    try:
                        en_name = ticker.info.get('longName', ticker.info.get('shortName', ''))
                    except Exception:
                        en_name = ""
                    if ch_name and en_name:
                        stock_name = f"{ch_name} ({en_name})"
                    else:
                        stock_name = ch_name or en_name or ""
                    name_display = f" 【{stock_name}】" if stock_name else ""

                    # 風控雷達邏輯 (台股紅多綠空)
                    if close_today <= p_lower:
                        action_word = "🟢 立刻賣出 (全面停損)"
                        action_color = "#28a745"
                        status_tag = "🚨 盤中破底趨勢轉空"
                        action_advice = "【危險】股價已無情跌破下關極限支撐！當沖可順勢偏空，波段持股請嚴格執行紀律，無條件出清停損！"
                    elif close_today < p_mid:
                        action_word = "🟡 保守觀望 (減碼防守)"
                        action_color = "#ffc107"
                        status_tag = "⚠️ 盤中中關失守轉弱"
                        action_advice = "【警告】股價處於中關之下，多方熄火。當沖切勿盲目追多，波段多單宜適度減碼防守。"
                    elif high_today >= p_upper and close_today < p_upper:
                        action_word = "🟠 分批停利 (獲利入袋)"
                        action_color = "#fd7e14"
                        status_tag = "🟢 盤中觸及上關受阻"
                        action_advice = "【調節】盤中曾強勢挑戰上關，但收盤前暫時拉回。如果是前幾天進場的波段單，此處利潤豐厚，建議先落袋部分資產。"
                    elif close_today >= p_upper:
                        action_word = "🔴 強勢持有 (順勢追多)"
                        action_color = "#dc3545"
                        status_tag = "💎 盤中強勢突破上關"
                        action_advice = "【噴出】短線動能極度強悍，成功踩在上關頭頂！當沖強勢追多點，波段多單請牢牢拿好讓利潤繼續奔跑！"
                    else:
                        action_word = "⚪ 安心持有 (軌道安全)"
                        action_color = "#6c757d"
                        status_tag = "✨ 中關之上常態震盪"
                        action_advice = "【安全】股價穩踩在中關之上常態整理，整體多頭軌道安全，持股不需要被盤面震盪影響，安心續抱即可。"

                    # 網頁呈現
                    st.write("---")
                    st.subheader(f"📊 股票：{stock_input}{name_display} 最新即時健檢報告")
                    
                    st.markdown(
                        f"""
                        <div style="background-color: {action_color}15; padding: 20px; border-radius: 10px; border: 2px solid {action_color}; text-align: center; margin-bottom: 25px;">
                            <span style="font-size: 16px; color: #666; font-weight: bold; display: block; margin-bottom: 5px;">💡 {stock_input} {ch_name} 盤中核心操盤動作</span>
                            <span style="font-size: 40px; color: {action_color}; font-weight: 900; letter-spacing: 2px;">{action_word}</span>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric(label="🕒 盤中最新價", value=f"{close_today} 元")
                    col2.metric(label="📈 盤中最高價", value=f"{high_today} 元")
                    col3.metric(label="📊 盤中成交量", value=f"{volume_today} 張")
                    
                    st.info(f"**目前多空狀態：** {status_tag}")
                    st.warning(f"**⚡ 盤中即時操盤建議：** {action_advice}")
                    
                    # ───【新增新功能：繪製專業 KD + 三關價 K 線圖（取最近一個月顯示）】───
                    st.write("### 📈 近一個月專業技術線圖 (K線 + 三關價 + KD指標)")
                    plot_df = df.iloc[-22:].copy() # 取最近一個月大約 22 個交易日
                    
                    # 建立雙子圖 (上面放K線，下面放KD)
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                        vertical_spacing=0.1, 
                                        row_width=[0.4, 0.6])
                    
                    # 1. 主圖：K線圖 (遵循台股紅漲綠跌習慣)
                    fig.add_trace(gr.Candlestick(
                        x=plot_df.index, open=plot_df['open'], high=plot_df['high'],
                        low=plot_df['low'], close=plot_df['close'], name='K線',
                        increasing_line_color='#dc3545', increasing_fill_color='#dc3545',
                        decreasing_line_color='#28a745', decreasing_fill_color='#28a745'
                    ), row=1, col=1)
                    
                    # 疊加當天最新的三關價水平防守線（用虛線標示在K線圖上做對照）
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=[p_upper]*len(plot_df), name='今日上關', line=dict(color='#fd7e14', width=1, dash='dash')), row=1, col=1)
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=[p_mid]*len(plot_df), name='今日中關', line=dict(color='#17a2b8', width=1, dash='dash')), row=1, col=1)
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=[p_lower]*len(plot_df), name='今日下關', line=dict(color='#28a745', width=1, dash='dash')), row=1, col=1)
                    
                    # 2. 副圖：KD 指標線
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=plot_df['K線'], name='K值 (9,3)', line=dict(color='#ffc107', width=1.5)), row=2, col=1)
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=plot_df['D線'], name='D值 (9,3)', line=dict(color='#17a2b8', width=1.5)), row=2, col=1)
                    
                    # KD 輔助超買超賣水平線
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=[80]*len(plot_df), name='超買區 (80)', line=dict(color='#dc3545', width=0.8, dash='dot'), showlegend=False), row=2, col=1)
                    fig.add_trace(gr.Scatter(x=plot_df.index, y=[20]*len(plot_df), name='超賣區 (20)', line=dict(color='#28a745', width=0.8, dash='dot'), showlegend=False), row=2, col=1)
                    
                    # 調整版面樣式
                    fig.update_layout(
                        height=500, margin=dict(l=10, r=10, t=10, b=10),
                        xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig.update_yaxes(title_text="股價 (元)", row=1, col=1)
                    fig.update_yaxes(title_text="KD值", range=[0, 100], row=2, col=1)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    # ──────────────────────────────────────────────────────────────
                    
                    # 三關價軌道詳細數據表
                    st.write("### 📌 今日三關價防守線對照")
                    pivot_df = pd.DataFrame({
                        "關鍵軌道位置": ["🟥 上關價 (極端壓力)", "⬜ 中關價 (多空分水嶺)", "🟩 下關價 (極限支撐)"],
                        "價格 (元)": [p_upper, p_mid, p_lower],
                        "與當前盤中價差距": [
                            f"相差 {round(p_upper - close_today, 2)} 元" if p_upper > close_today else "🔥 已突破",
                            f"高出 {round(close_today - p_mid, 2)} 元" if close_today > p_mid else f"低於 {round(p_mid - close_today, 2)} 元",
                            f"高出 {round(close_today - p_lower, 2)} 元" if close_today > p_lower else "🚨 已跌破"
                        ]
                    })
                    st.table(pivot_df)
                    
                    st.caption(f"數據更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (每刷新網頁或更換代號即自動抓取最新報表)")
                    
            except Exception as err:
                st.error(f"❌ 診斷過程中發生錯誤: {err}")
