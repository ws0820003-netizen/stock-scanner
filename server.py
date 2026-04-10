from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import uvicorn
import os
import certifi

app = FastAPI()

# 允許跨網域連線 (讓 GitHub Pages 可以連過來)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 從環境變數抓取冰箱鑰匙
MONGO_URI = os.environ.get("MONGO_URI")

print("🔌 正在連線至雲端大冰箱...")
# 💡 加上 certifi 憑證與 ServerApi，確保雲端連線穩定
client = MongoClient(MONGO_URI, server_api=ServerApi('1'), tlsCAFile=certifi.where())
db = client['StockScanner']
collection = db['StockData']
print("✅ 冰箱連線成功！")

# ==========================================
# 共通邏輯：根據產業過濾資料
# ==========================================
def get_filtered_stocks(industry_filter):
    query = {}
    if industry_filter and industry_filter != "全部":
        query["industry"] = industry_filter
    return list(collection.find(query, {"_id": 0}))

# ==========================================
# 引擎 1：手繪型態比對 API
# ==========================================
@app.post("/api/scan")
async def scan_pattern(request: Request):
    data = await request.json()
    user_pattern = data.get("pattern", [])
    industry = data.get("industry", "全部") # 💡 接收產業參數
    
    if not user_pattern or len(user_pattern) != 60:
        return {"status": "error", "message": "圖形資料不正確"}

    all_stocks = get_filtered_stocks(industry)
    
    results = []
    for stock in all_stocks:
        stock_norm = stock.get("norm", [])
        if len(stock_norm) == 60:
            total_error = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
            score = max(0, 100 - (total_error * 2.5))
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock.get("name", "未知"),     # 💡 回傳中文名稱
                "industry": stock.get("industry", ""), # 💡 回傳產業
                "score": round(score, 1),
                "prices": stock["raw"]
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

# ==========================================
# 引擎 2：底部爆量反轉 API
# ==========================================
@app.post("/api/scan_volume_surge")
async def scan_volume_surge(request: Request):
    data = await request.json()
    industry = data.get("industry", "全部")
    
    all_stocks = get_filtered_stocks(industry)
        
    results = []
    for stock in all_stocks:
        prices = stock.get("raw", [])
        volumes = stock.get("volume", [])
        
        if len(prices) < 60 or len(volumes) < 60:
            continue
            
        today_vol, today_price, yesterday_price = volumes[-1], prices[-1], prices[-2]
        avg_vol_10d = sum(volumes[-11:-1]) / 10 if sum(volumes[-11:-1]) > 0 else 1
        
        # 策略：上漲 + 2.5倍量 + 千張以上
        if today_price > yesterday_price and today_vol > (avg_vol_10d * 2.5) and today_vol > 1000000:
            surge_ratio = round(today_vol / avg_vol_10d, 1)
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock.get("name", "未知"),
                "industry": stock.get("industry", ""),
                "score": surge_ratio, 
                "prices": prices
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:15]}

# ==========================================
# 引擎 3：🤖 AI 經典型態辨識 API
# ==========================================
@app.post("/api/scan_ai_pattern")
async def scan_ai_pattern(request: Request):
    data = await request.json()
    pattern_type = data.get("pattern_type", "W_BOTTOM")
    industry = data.get("industry", "全部")
    
    # 數學模板
    ideal_pattern = []
    if pattern_type == "W_BOTTOM":
        ideal_pattern = [1-(i/14) for i in range(15)] + [(i/14)*0.5 for i in range(15)] + [0.5-(i/14)*0.5 for i in range(15)] + [i/14 for i in range(15)]
    elif pattern_type == "M_TOP":
        ideal_pattern = [(i/14) for i in range(15)] + [1-(i/14)*0.5 for i in range(15)] + [0.5+(i/14)*0.5 for i in range(15)] + [1-(i/14) for i in range(15)]
    elif pattern_type == "V_BOTTOM":
        ideal_pattern = [1-(i/29) for i in range(30)] + [(i/29) for i in range(30)]
    elif pattern_type == "A_TOP":
        ideal_pattern = [(i/29) for i in range(30)] + [1-(i/29) for i in range(30)]

    all_stocks = get_filtered_stocks(industry)
    
    results = []
    for stock in all_stocks:
        stock_norm = stock.get("norm", [])
        if len(stock_norm) == 60:
            total_error = sum(abs(a - b) for a, b in zip(ideal_pattern, stock_norm))
            score = max(0, 100 - (total_error * 2.5))
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock.get("name", "未知"),
                "industry": stock.get("industry", ""),
                "score": round(score, 1),
                "prices": stock["raw"]
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
