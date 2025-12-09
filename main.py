from fastapi import FastAPI, HTTPException
import akshare as ak
import pandas as pd
from typing import Optional

app = FastAPI()

# 1. Stock Data (History)
@app.get("/history")
def get_history(symbol: str, period: str = "daily"):
    try:
        # AkShare: History A-Share
        # symbol expects "600519"
        df = ak.stock_zh_a_hist(symbol=symbol, period=period, adjust="qfq")
        df = df[['日期', '开盘', '最高', '最低', '收盘', '成交量']]
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Screener (Market Snapshot)
@app.get("/snapshot")
def get_snapshot():
    # Fetches real-time data for ALL 5000+ stocks
    # Columns: code, name, trade, pricechange, changepercent, buy, sell, settlement, open, high, low, volume, amount, mktcap, ...
    df = ak.stock_zh_a_spot_em()
    # Rename for consistency with your app
    rename_map = {
        '代码': 'symbol', '名称': 'name', '最新价': 'price', 
        '涨跌幅': 'changePercent', '市盈率-动态': 'pe', '市净率': 'pb', 
        '总市值': 'marketCap', '换手率': 'turnover'
    }
    df = df.rename(columns=rename_map)
    # Filter only what we need to keep JSON light
    return df[list(rename_map.values())].to_dict(orient="records")

# 3. News
@app.get("/news")
def get_news(symbol: Optional[str] = None):
    # AkShare has various news sources. Example: EastMoney
    # If symbol is provided, get specific stock news
    if symbol:
        df = ak.stock_news_em(symbol=symbol)
        df = df[['发布时间', '文章标题', '文章链接']]
        df.columns = ['publishedAt', 'headline', 'url']
    else:
        # General Market News (CCTV or Similar)
        df = ak.stock_info_global_cls(symbol="A股24小时电报") # Cailian Press
        df = df[['time', 'content']]
        df.columns = ['publishedAt', 'headline']
        df['url'] = "" # Cailian often has no link
    
    return df.head(20).to_dict(orient="records")

# 4. Market Status / Indices
@app.get("/markets")
def get_markets():
    # Get Major Indices (ShangZheng, ShenZheng, etc.)
    df = ak.stock_zh_index_spot()
    return df.to_dict(orient="records")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
