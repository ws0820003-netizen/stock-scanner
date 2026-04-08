from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import uvicorn
import requests
import urllib3

# 關閉煩人的 HTTPS 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI()

# 🛡️ CORS 設定：允許網頁跨域連線
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

stock_cache = {}

# ==========================================
# 💾 啟動時建立全台股 60日 快取資料庫 (終極防封鎖批次版)
# ==========================================
@app.on_event("startup")
def load_data():
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

    print(f"\n⏳ 步驟 2：啟動「批次下載模式」，向 Yahoo Finance 索取資料 (速度更快、防封鎖)...")
    
    chunk_size = 100 # 每 100 檔打包成一次請求
    success_count = 0
    
    # 迴圈：每次切 100 檔出來抓資料
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i + chunk_size]
        try:
            # 批量下載這 100 檔 (Yahoo 會一次回傳一個超大表格)
            df = yf.download(chunk, period="6mo", progress=False)
            
            if df.empty or 'Close' not in df:
                continue
                
            close_df = df['Close']
            
            # 預防這包剛好只有 1 檔股票的情況
            if isinstance(close_df, pd.Series):
                close_df = close_df.to_frame(name=chunk[0])
            
            # 從大表格中把每一檔股票的資料抽出來
            for ticker in chunk:
                if ticker in close_df.columns:
                    # 拔除空值，並取最後 60 筆
                    prices = close_df[ticker].dropna().tail(60).values.flatten().tolist()
                    
                    if len(prices) >= 60:
                        min_p, max_p = min(prices), max(prices)
                        # 正規化處理
                        norm_prices = [(p - min_p) / (max_p - min_p) if max_p != min_p else 0 for p in prices]
                        stock_cache[ticker] = {"raw": prices, "norm": norm_prices}
                        success_count += 1
                        
        except Exception as e:
            print(f"  ⚠️ 批次下載發生錯誤: {e}")
            
        # 顯示進度
        current = min(i + chunk_size, len(stock_list))
        print(f"  ...下載進度: {current}/{len(stock_list)} (已成功庫存: {success_count} 檔)")

    print(f"\n🚀 霸氣全開！全市場資料庫建立完成，共就緒 {len(stock_cache)} 檔股票。等待網頁呼叫...\n")


# ==========================================
# 🧠 AI 比對核心 API (MAE 極速版)
# ==========================================
@app.post("/api/scan")
async def scan_pattern(request: Request):
    data = await request.json()
    user_pattern = data.get("pattern", [])
    
    # 確保有收到資料，且剛好是 60 個點
    if not user_pattern or len(user_pattern) != 60:
        return {"status": "error", "message": "圖形資料不正確或點數不符"}

    results = []
    
    for ticker, stock_data in stock_cache.items():
        stock_norm = stock_data["norm"]
        
        # 💡 使用 MAE (絕對值誤差總和)，取代會當機的 fastdtw，速度快 100 倍！
        total_error = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
        
        # 將誤差轉換為相似度分數 0~100 (靈敏度係數 2.5)
        score = max(0, 100 - (total_error * 2.5))
        
        results.append({
            "code": ticker.split('.')[0],
            "name": ticker,
            "score": round(score, 1),
            "prices": stock_data["raw"]
        })

    # 依照相似度排序，回傳前 10 名
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

# ==========================================
# 啟動伺服器
# ==========================================
import os

if __name__ == "__main__":
    # 讓程式自動抓取 Render 分配的 Port，如果抓不到就預設 8000
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 啟動 Python API 伺服器於 Port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port)
