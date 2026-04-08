from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import uvicorn
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🔑 這裡要貼上你的大冰箱鑰匙 (記得換成真實密碼)
# ==========================================
MONGO_URI = "mongodb+srv://CHUWEI_db_user:WRuvF2a58TtjVzJP@cluster0.vqvofve.mongodb.net/?appName=Cluster0"

print("🔌 正在連線至雲端大冰箱...")
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
db = client['StockScanner']
collection = db['StockData']
print("✅ 冰箱連線成功！")

# ==========================================
# 🧠 AI 比對核心 API (直接開冰箱拿資料)
# ==========================================
@app.post("/api/scan")
async def scan_pattern(request: Request):
    data = await request.json()
    user_pattern = data.get("pattern", [])
    
    if not user_pattern or len(user_pattern) != 60:
        return {"status": "error", "message": "圖形資料不正確或點數不符"}

    # 💡 絕招：直接從冰箱把所有股票拿出來 (耗時極短)
    try:
        all_stocks = list(collection.find({}, {"_id": 0})) 
    except Exception as e:
        return {"status": "error", "message": f"讀取冰箱失敗：{e}"}
    
    if not all_stocks:
         return {"status": "error", "message": "冰箱裡沒有資料！請確認進貨腳本是否有成功執行。"}

    results = []
    for stock in all_stocks:
        stock_norm = stock.get("norm", [])
        # 防呆：確保資料完整才計算
        if len(stock_norm) == 60:
            total_error = sum(abs(a - b) for a, b in zip(user_pattern, stock_norm))
            score = max(0, 100 - (total_error * 2.5))
            
            results.append({
                "code": stock["ticker"].split('.')[0], # 去掉 .TW 或 .TWO
                "name": stock["ticker"],
                "score": round(score, 1),
                "prices": stock["raw"]
            })

    # 排序並取出前 10 名
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "success", "matches": results[:10]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 啟動 Python API 伺服器於 Port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port)