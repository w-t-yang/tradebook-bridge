from fastapi import FastAPI, HTTPException
import akshare as ak
import pandas as pd
from typing import Optional

app = FastAPI()

# 1. Root / Health Check
@app.get("/")
def read_root():
    return {"status": "ok", "server": "akshare_bridge"}

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
    df = ak.stock_zh_a_spot()
    # Rename for consistency with your app
    # Note: stock_zh_a_spot does not return PE, PB, MarketCap, Turnover
    rename_map = {
        '代码': 'symbol', '名称': 'name', '最新价': 'price', 
        '涨跌幅': 'changePercent', 
        '成交量': 'volume', '成交额': 'amount',
        '昨收': 'prevClose', '今开': 'open',
        '最高': 'high', '最低': 'low'
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
        df = df[['发布时间', '新闻标题', '新闻链接']]
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
    # Using Sina source as it is more reliable and available
    df = ak.stock_zh_index_spot_sina()
    rename_map = {
        '代码': 'symbol', '名称': 'name', '最新价': 'price', 
        '涨跌额': 'change', '涨跌幅': 'changePercent', 
        '昨收': 'prevClose', '今开': 'open', 
        '最高': 'high', '最低': 'low', 
        '成交量': 'volume', '成交额': 'amount'
    }
    df = df.rename(columns=rename_map)
    return df.to_dict(orient="records")

# 5. Sectors
@app.get("/sectors")
def get_sectors():
    try:
        # EastMoney Industry Boards
        df = ak.stock_board_industry_name_em()
        # Columns: 排名, 板块名称, 相关链接, 最新价, 涨跌额, 涨跌幅, 总市值, 换手率, 上涨家数, 下跌家数, 领涨股票, 领涨股票-涨跌幅
        rename_map = {
            '板块名称': 'name',
            '涨跌幅': 'change', # This is usually a percentage number like 1.23
        }
        df = df.rename(columns=rename_map)
        
        # Format change to string with % if needed, or keep as number. 
        # CustomDataProvider expects CustomDataProvider to handle it or Server to return it?
        # CustomDataProvider.ts getSectors returns empty array currently.
        # Let's return a format that matches SectorPerformance in types.ts roughly:
        # { name, filterKey, change, isUp, color }
        # But server should return raw data, CustomDataProvider maps it.
        # Let's return: { name, changePercent }
        
        results = []
        for _, row in df.iterrows():
            change_pct = row['change']
            results.append({
                'name': row['name'],
                'change': f"{change_pct}%", # String format
                'isUp': change_pct >= 0
            })
        return results
    except Exception as e:
        print(f"Error fetching sectors: {e}")
        return []

# 6. Events
@app.get("/events")
def get_events():
    try:
        # Economic Calendar
        # ak.macro_china_money_supply() ? No, that's data.
        # ak.news_cctv_baidu() ?
        # Let's use a simple macro data source or return empty if complex.
        # For now, let's mock some events or use a reliable macro function if known.
        # ak.macro_china_cpi_yearly() returns historical data.
        
        # Let's return a static list or fetch real news as events?
        # Ideally we want an economic calendar.
        # ak.economic_calendar() exists in some versions?
        # Let's stick to returning a structure that CustomDataProvider can map.
        return [] 
    except Exception:
        return []

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="AkShare Bridge Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port)
