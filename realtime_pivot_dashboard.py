import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import requests
import re

# 網頁基本設定
st.set_page_config(page_title="盤中即時三關價風控儀表板", page_icon="📈", layout="centered")

st.title("📈 盤中即時三關價 ＆ 出場風控雷達")
st.markdown("輸入台股股票代號，立刻獲取**此時此刻盤中最新價**與三關價防守位置。")

# ───【核心修正：專門抓取台灣本土中文名稱的函數】───
def get_taiwan_chinese_name(symbol):
    try:
        # 直接連線台灣奇摩股市，抓取網頁標題
        url = f"https://tw.stock.yahoo.com/quote/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            # 從 <title> 標籤中切出中文名稱 (例如 "台積電 (2330) - 個股走勢" -> "台積電")
            title_match = re.search(r'<title>(.*?)</title>', res.text)
            if title_match:
                title_text = title_match.group(1)
                chinese_name = title_text.split('(')[0].strip()
                if chinese_name and "Yahoo" not in chinese_name and "找不到" not in chinese_name:
                    return chinese_name
    except Exception:
        pass
    return ""
# ──────────────────────────────────────────────────

# 1. 介面輸入
stock_input = st.text_input("🔍 請輸入台股代號（例如：2330, 2317, 8908）：", "2330").strip()

if stock_input:
    ticker_id = f"{stock_input}.TW"
    
    with st.spinner(f"🚀 正在即時連線抓取 {stock_input} 最新盤中數據..."):
        try:
            # 2. 建立 Ticker 物件與下載日 K 線
            ticker = yf.Ticker(ticker_id)
            stock_data = yf.download(ticker_id, period="5d", interval="1d", progress=False)
            
            # 同時抓取中文與英文名稱
            ch_name = get_taiwan_chinese_name(stock_input)
            try:
                en_name = ticker.info.get('longName', ticker.info.get('shortName', ''))
            except Exception:
                en_name = ""
            
            # 漂亮地組合名稱
            if ch_name and en_name:
                stock_name = f"{ch_name} ({en_name})"
            else:
                stock_name = ch_name or en_name or ""
                
            name_display = f" 【{stock_name}】" if stock_name else ""
            
            if stock_data.empty or len(stock_data) < 2:
                st.error("❌ 找不到該股票數據，請確認代號是否正確（目前僅支援上市櫃股票）。")
            else:
                df = stock_data.dropna().copy()
                
                # 自動智慧智慧掃描，剝離 yfinance 多重索引地雷
                if isinstance(df.columns, pd.MultiIndex):
                    for level in range(df.columns.nlevels):
                        labels = [str(c).lower() for c in df.columns.get_level_values(level)]
                        if 'close' in labels:
                            df.columns = df.columns.get_level_values(level)
                            break
                
                # 強制全部轉成標準小寫字串
                df.columns = [str(c).lower() for c in df.columns]
                
                # 提取最新（今天盤中）與昨日數據
                close_today = round(float(df['close'].iloc[-1]), 2)
                high_today = round(float(df['high'].iloc[-1]), 2)
                low_today = round(float(df['low'].iloc[-1]), 2)
                volume_today = int(df['volume'].iloc[-1] / 1000)
                
                h_prev = float(df['high'].iloc[-2])
                l_prev = float(df['low'].iloc[-2])
                
                # 3. 三關價核心公式
                p_upper = round(l_prev + (h_prev - l_prev) * 1.382, 2)  # 上關
                p_mid = round((h_prev + l_prev) / 2, 2)                 # 中關
                p_lower = round(h_prev - (h_prev - l_prev) * 1.382, 2)  # 下關
                
                # 4. 盤中即時多空位置 ＆ 終極大字指令判定 (堅持台股紅多綠空邏輯)
                if close_today <= p_lower:
                    action_word = "🟢 立刻賣出 (全面停損)"
                    action_color = "#28a745" # 台股跌/綠色
                    status_tag = "🚨 盤中破底趨勢轉空"
                    action_advice = "【危險】股價已無情跌破下關極限支撐！當沖可順勢偏空，波段持股請嚴格執行紀律，無條件出清停損！"
                elif close_today < p_mid:
                    action_word = "🟡 保守觀望 (減碼防守)"
                    action_color = "#ffc107" # 警告/黃色
                    status_tag = "⚠️ 盤中中關失守轉弱"
                    action_advice = "【警告】股價處於中關之下，多方熄火。當沖切勿盲目追多，波段多單宜適度減碼防守。"
                elif high_today >= p_upper and close_today < p_upper:
                    action_word = "🟠 分批停利 (獲利入袋)"
                    action_color = "#fd7e14" # 橘色
                    status_tag = "🟢 盤中觸及上關受阻"
                    action_advice = "【調節】盤中曾強勢挑戰上關，但收盤前暫時拉回。如果是前幾天進場的波段單，此處利潤豐厚，建議先落袋部分資產。"
                elif close_today >= p_upper:
                    action_word = "🔴 強勢持有 (順勢追多)"
                    action_color = "#dc3545" # 台股漲/紅色
                    status_tag = "💎 盤中強勢突破上關"
                    action_advice = "【噴出】短線動能極度強悍，成功踩在上關頭頂！當沖強勢追多點，波段多單請牢牢拿好讓利潤繼續奔跑！"
                else:
                    action_word = "⚪ 安心持有 (軌道安全)"
                    action_color = "#6c757d" # 常態灰色
                    status_tag = "✨ 中關之上常態震盪"
                    action_advice = "【安全】股價穩踩在中關之上常態整理，整體多頭軌道安全，持股不需要被盤面震盪影響，安心續抱即可。"

                # 5. 網頁視覺化呈現
                st.write("---")
                st.subheader(f"📊 股票：{stock_input}{name_display} 最新即時健檢報告")
                
                # 大字直覺圖章
                st.markdown(
                    f"""
                    <div style="background-color: {action_color}15; padding: 20px; border-radius: 10px; border: 2px solid {action_color}; text-align: center; margin-bottom: 25px;">
                        <span style="font-size: 16px; color: #666; font-weight: bold; display: block; margin-bottom: 5px;">💡 {stock_input} {ch_name} 盤中核心操盤動作</span>
                        <span style="font-size: 40px; color: {action_color}; font-weight: 900; letter-spacing: 2px;">{action_word}</span>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # 數據指標
                col1, col2, col3 = st.columns(3)
                col1.metric(label="🕒 盤中最新價", value=f"{close_today} 元")
                col2.metric(label="📈 盤中最高價", value=f"{high_today} 元")
                col3.metric(label="📊 盤中成交量", value=f"{volume_today} 張")
                
                # 顯示詳細狀態說明
                st.info(f"**目前多空狀態：** {status_tag}")
                st.warning(f"**⚡ 盤中即時操盤建議：** {action_advice}")
                
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
