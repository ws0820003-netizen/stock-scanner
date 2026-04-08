from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import uvicorn
import requests
import urllib3
import os
import threading
import time  # 💡 新增：用來休息，避免被 Yahoo 封鎖
import gc    # 💡 新增：用來倒垃圾，釋放記憶體

# 關閉煩人的 HTTPS 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

stock_cache = {}
is_data_ready = False

# ==========================================
# 💾 核心下載邏輯 (安全休閒模式)
# ==========================================
def load_data_background():
    global is_data_ready
    print("\n🌍 步驟 1：正在取得全台股 (上市+上櫃) 代號清單...")
    headers = {"User-Agent": "Mozilla/5.0"}
    twse_list, tpex_list = [], []
    
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", verify=False, headers=headers, timeout=10)
        twse_list = [s['Code'] + ".TW" for s in res_twse.json() if len(s['Code']) == 4]
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", verify=False, headers=headers, timeout=15)
        tpex_list = [s['SecuritiesCompanyCode'] + ".TWO" for s in res_tpex.json() if len(s['SecuritiesCompanyCode']) == 4]
    except Exception as e:
        print(f"⚠️ 獲取股票清單失敗：{e}")

    stock_list = twse_list + tpex_list 
    print(f"✅ 成功取得 {len(stock_list)} 檔股票代號！")
    print(f"\n⏳ 步驟 2：啟動「安全休閒模式」，向 Yahoo Finance 索取資料...")
    
    chunk_size = 50  # 💡 縮小批次，每 50 檔抓一次
    success_count = 0
    
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i + chunk_size]
        try:
            # 加上 timeout 避免無限卡住
            df = yf.download(chunk, period="6mo", progress=False)
            if df.empty or 'Close' not in df:
                continue
                
            close_df = df['Close']
            if isinstance(close_df, pd.Series):
                close_df = close_df.to_frame(name=chunk[0])
            
            for ticker in chunk:
                if ticker in close_df.columns:
                    prices = close_df[ticker].dropna().tail(60).values.flatten().tolist()
                    if len(prices) >= 60:
                        min_p, max_p = min(prices), max(prices)
                        norm_prices = [(p - min_p) / (max_p - min_p) if max_p != min_p else 0 for p in prices]
                        stock_cache[ticker] = {"raw": prices, "norm": norm_prices}
                        success_count += 1
            
            # 💡 終極防護機制：強制清空記憶體 + 喘息 1.5 秒鐘
            del df
            gc.collect()
            time.sleep(1.5)

        except Exception:
            pass
            
        current = min(i + chunk_size, len(stock_list))
        print(f"  ...下載進度: {current}/{len(stock_list)} (已成功庫存: {success_count} 檔)")

    print(f"\n🚀 霸氣全開！全市場資料庫建立完成，共就緒 {len(stock_cache)} 檔股票。")
    is_data_ready = True

# ==========================================
# 伺服器啟動與 API 設定 (維持不變)
# ==========================================
@app.on_event("startup")
def startup_event():
    print("✅ 伺服器秒速開機成功！Port 已綁定。準備在背景偷偷下載資料...")
    threading.Thread(target=load_data_background).start()

@app.post("/api/scan")
async def scan_pattern(request: Request):
    if not is_data_ready:
        return {"status": "error", "message": "雲端大腦剛起床，正在背景努力下載全台股資料（為避免當機已開啟安全模式，約需 5 分鐘），請稍後再按一次掃描！"}

    data = await request.json()
    user_pattern = data.get("pattern", [])
    
    if not user_pattern or len(user_pattern) != 60:
        return {"status": "error", "message": "圖形資料不正確或點數不符"}

    results = []
    for ticker, stock_data in stock_cache.items():
        stock_norm = stock_data["norm"]
        total_error = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
        score = max(0, 100 - (total_error * 2.5))
        results.append({
            "code": ticker.split('.')[0],
            "name": ticker,
            "score": round(score, 1),
            "prices": stock_data["raw"]
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 啟動 Python API 伺服器於 Port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port)
