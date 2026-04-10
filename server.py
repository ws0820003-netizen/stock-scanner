from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import os
import certifi

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 💡 從環境變數讀取 MONGO_URI
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI, server_api=ServerApi('1'), tlsCAFile=certifi.where())
db = client['StockScanner']
collection = db['StockData']

@app.post("/api/scan")
async def scan_pattern(request: Request):
    data = await request.json()
    user_pattern = data.get("pattern", [])
    industry = data.get("industry", "全部")
    
    query = {} if industry == "全部" else {"industry": industry}
    all_stocks = list(collection.find(query, {"_id": 0}))
    
    results = []
    for stock in all_stocks:
        stock_norm = stock.get("norm", [])
        if len(stock_norm) == 60:
            err = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
            score = max(0, 100 - (err * 2.5))
            results.append({
                "code": stock["ticker"].split('.')[0],
                "name": stock.get("name", "未知"),
                "industry": stock.get("industry", "其他"),
                "score": round(score, 1),
                "prices": stock["raw"]
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

@app.post("/scan_volume_surge")
async def scan_volume_surge(request: Request):
    data = await request.json()
    industry = data.get("industry", "全部")
    query = {} if industry == "全部" else {"industry": industry}
    
    all_stocks = list(collection.find(query, {"_id": 0}))
    results = []
    for stock in all_stocks:
        prices, volumes = stock.get("raw", []), stock.get("volume", [])
        if len(prices) < 60 or len(volumes) < 60: continue
        avg_vol_10d = sum(volumes[-11:-1]) / 10 if sum(volumes[-11:-1]) > 0 else 1
        if prices[-1] > prices[-2] and volumes[-1] > (avg_vol_10d * 2.5) and volumes[-1] > 1000000:
            results.append({
                "code": stock["ticker"].split('.')[0], "name": stock.get("name", "未知"),
                "industry": stock.get("industry", "其他"),
                "score": round(volumes[-1] / avg_vol_10d, 1), "prices": prices
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:15]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
