from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import uvicorn
import os
import certifi

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.environ.get("MONGO_URI")

print("🔌 正在連線至雲端大冰箱...")
# 帶上 certifi 憑證，確保 Render 不會被擋
client = MongoClient(MONGO_URI, server_api=ServerApi('1'), tlsCAFile=certifi.where())
db = client['StockScanner']
collection = db['StockData']
print("✅ 冰箱連線成功！")

# ==========================================
# 引擎 1：手繪型態比對 API
# ==========================================
@app.post("/api/scan")
async def scan_pattern(request: Request):
    data = await request.json()
    user_pattern = data.get("pattern", [])
    
    if not user_pattern or len(user_pattern) != 60:
        return {"status": "error", "message": "圖形資料不正確"}

    try:
        all_stocks = list(collection.find({}, {"_id": 0})) 
    except Exception as e:
        return {"status": "error", "message": f"讀取冰箱失敗：{e}"}
    
    results = []
    for stock in all_stocks:
        stock_norm = stock.get("norm", [])
        if len(stock_norm) == 60:
            total_error = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
            score = max(0, 100 - (total_error * 2.5))
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock["ticker"],
                "score": round(score, 1),
                "prices": stock["raw"]
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

# ==========================================
# 引擎 2：底部爆量反轉 API
# ==========================================
@app.post("/api/scan_volume_surge")
async def scan_volume_surge():
    try:
        all_stocks = list(collection.find({}, {"_id": 0})) 
    except Exception as e:
        return {"status": "error", "message": f"讀取冰箱失敗：{e}"}
        
    results = []
    
    for stock in all_stocks:
        prices = stock.get("raw", [])
        volumes = stock.get("volume", [])
        
        if len(prices) < 60 or len(volumes) < 60:
            continue
            
        today_vol = volumes[-1]
        today_price = prices[-1]
        yesterday_price = prices[-2]
        
        # 過去 10 天平均成交量 (窒息量基準)
        avg_vol_10d = sum(volumes[-11:-1]) / 10 if sum(volumes[-11:-1]) > 0 else 1
        
        # 策略邏輯：
        # 1. 股價上漲 (紅K)
        # 2. 今天成交量是過去10天均量的 2.5 倍以上
        # 3. 今天成交量大於 1000 張 (1,000,000 股)
        is_price_up = today_price > yesterday_price
        is_vol_surge = today_vol > (avg_vol_10d * 2.5)
        is_enough_vol = today_vol > 1000000 
        
        if is_price_up and is_vol_surge and is_enough_vol:
            surge_ratio = round(today_vol / avg_vol_10d, 1)
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock["ticker"],
                "score": surge_ratio, # 這裡是放大的倍數
                "prices": prices
            })

    # 依照爆發倍數排序
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:15]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 啟動 Python API 伺服器於 Port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port)
