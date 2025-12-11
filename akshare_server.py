from fastapi import FastAPI, HTTPException
import akshare as ak
import pandas as pd
from typing import Optional
import yfinance as yf
from yfinance import EquityQuery

app = FastAPI()

# 1. Root / Health Check
@app.get("/")
def read_root():
    return {"status": "ok", "server": "akshare_bridge"}

def safe_float(val):
    try:
        if val is None: return None
        return float(val)
    except (ValueError, TypeError):
        return None


# 1. Stock Data (History)
@app.get("/history")
def get_history(symbol: str, period: str = "5y", interval: str = "1d"):
    try:
        # AkShare: History A-Share
        # symbol expects "600519"
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20190707", adjust="qfq")
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
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = ak.stock_zh_a_spot_em()
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Failed to fetch snapshot after {max_retries} attempts: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch market data: {str(e)}")
            import time
            time.sleep(1)
            continue
    
    # Rename for consistency with your app
    rename_map = {
        '代码': 'symbol', 
        '名称': 'name', 
        '最新价': 'price', 
        '涨跌幅': 'changePercent', 
        '涨跌额': 'change',
        '成交量': 'volume', 
        '成交额': 'amount',
        '振幅': 'amplitude',
        '换手率': 'turnoverRate',
        '市盈率-动态': 'peRatio',
        '量比': 'volumeRatio',
        '5分钟涨跌': 'fiveMinChange',
        '最高': 'high', 
        '最低': 'low',
        '今开': 'open',
        '昨收': 'prevClose',
        '总市值': 'totalMarketCap',
        '流通市值': 'floatMarketCap',
        '涨速': 'riseSpeed',
        '市净率': 'pbRatio',
        '60日涨跌幅': 'sixtyDayChange',
        '年初至今涨跌幅': 'ytdChange'
    }
    
    # Rename columns that exist
    df = df.rename(columns=rename_map)
    
    # Filter only mapped columns to keep JSON clean but comprehensive
    available_cols = [col for col in rename_map.values() if col in df.columns]
    
    return df[available_cols].to_dict(orient="records")

# 3. News
@app.get("/news")
def get_news(symbol: Optional[str] = None):
    # AkShare has various news sources. Example: EastMoney
    # If symbol is provided, get specific stock news
    if symbol:
        df = ak.stock_news_em(symbol=symbol)
        # Check available columns, usually: 发布时间, 新闻标题, 新闻内容, 新闻链接
        # We'll use title as summary if content is missing
        df = df[['发布时间', '新闻标题', '新闻链接']]
        df.columns = ['publishedAt', 'headline', 'url']
        df['source'] = "East Money"
        df['summary'] = df['headline'] # Use headline as summary
    else:
        # General Market News (CCTV or Similar)
        df = ak.stock_info_global_cls(symbol="A股24小时电报") # Cailian Press
        df = df[['time', 'content']]
        df.columns = ['publishedAt', 'headline']
        df['url'] = "" # Cailian often has no link
        df['source'] = "East Money" # Or "Cailian Press" but user asked for East Money default
        df['summary'] = df['headline']
    
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

# 7. Screener (via yfinance)
@app.get("/screener")
def get_screener_results(sector: str = "Technology"):
    """
    Get screener results for a specific sector using yfinance.screener with region='cn'.
    Returns a list of stock info objects.
    """
    try:
        # Map sector to valid yfinance sector names (Title Case)
        valid_sector = sector.title() 
        
        try:
            # Construct composite query: Sector AND Region=CN
            q = EquityQuery('and', [
                EquityQuery('eq', ['sector', valid_sector]),
                EquityQuery('eq', ['region', 'cn'])
            ])
            response = yf.screen(q, count=100, size=100, sortField='intradaymarketcap', sortAsc=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Screener query failed for sector '{valid_sector}': {str(e)}")
            
        if not response or 'quotes' not in response:
             return []

        results = []
        quotes = response['quotes']
        
        for quote in quotes:
            symbol = quote.get('symbol')
            if not symbol:
                continue
            
            # Map screen result to StockInfo format
            stock_data = {
                "symbol": symbol,
                "name": quote.get("longName") or quote.get("shortName") or "N/A",
                "exchange": quote.get("exchange") or "N/A",
                "currency": quote.get("currency") or "N/A",
                "country": "China", # We know it's CN region
                "sector": valid_sector,
                "industry": "N/A",
                "marketCap": safe_float(quote.get("marketCap")),
                "description": "N/A",
                "website": "N/A",
                "ceo": "N/A",
                "employees": None,
                "founded": None,
                "ipoDate": quote.get("firstTradeDateEpochUtc"),
                # Real-time price data
                "price": quote.get("regularMarketPrice"),
                "change": quote.get("regularMarketChange"),
                "changePercent": quote.get("regularMarketChangePercent"),
                # Financials
                "trailingPE": quote.get("trailingPE"),
                "forwardPE": quote.get("forwardPE"),
                "priceToBook": quote.get("priceToBook"),
                "dividendYield": quote.get("dividendYield"),
                "beta": quote.get("beta"),
                "fiftyTwoWeekHigh": quote.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": quote.get("fiftyTwoWeekLow"),
                "averageVolume": safe_float(quote.get("averageDailyVolume3Month")),
                "trailingEps": quote.get("epsTrailingTwelveMonths"),
                "forwardEps": quote.get("epsForward")
            }
            results.append(stock_data)
                
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screener error: {str(e)}")

# Stock Info Endpoint
@app.get("/info/{symbol}")
def get_stock_info(symbol: str):
    try:
        # AkShare provides stock_individual_info_em for A-shares
        # Try to get basic info
        info_df = ak.stock_individual_info_em(symbol=symbol)
        
        # info_df is a DataFrame with columns: item, value
        # Convert to dict for easier access
        info_dict = dict(zip(info_df['item'], info_df['value']))
        
        # Try to get additional sector/industry info
        try:
            # Get stock board info
            board_df = ak.stock_board_industry_name_em()
            # This might not have direct mapping, so we'll use N/A
            sector = "N/A"
            industry = "N/A"
        except:
            sector = "N/A"
            industry = "N/A"
        
        return {
            "symbol": symbol,
            "name": info_dict.get("股票简称", "N/A"),
            "exchange": info_dict.get("上市时间", "N/A"),  # Using listing date as exchange info
            "currency": "CNY",  # Chinese stocks are in CNY
            "country": "China",
            "sector": sector,
            "industry": info_dict.get("行业", "N/A"),
            "marketCap": safe_float(info_dict.get("总市值")),
            "description": "N/A",  # AkShare doesn't provide company description
            "website": "N/A",
            "ceo": "N/A",
            "employees": None,
            "founded": None,
            "ipoDate": info_dict.get("上市时间", "N/A"),
            # Financials (Not available in stock_individual_info_em)
            "trailingPE": "N/A",
            "forwardPE": "N/A",
            "priceToBook": "N/A",
            "dividendYield": "N/A",
            "beta": "N/A",
            "fiftyTwoWeekHigh": "N/A",
            "fiftyTwoWeekLow": "N/A",
            "averageVolume": "N/A",
            "trailingEps": "N/A",
            "forwardEps": "N/A"
        }
    except Exception as e:
        # Fallback: return minimal info
        return {
            "symbol": symbol,
            "name": symbol,
            "exchange": "N/A",
            "currency": "CNY",
            "country": "China",
            "sector": "N/A",
            "industry": "N/A",
            "marketCap": None,
            "description": "N/A",
            "website": "N/A",
            "ceo": "N/A",
            "employees": None,
            "founded": None,
            "ipoDate": "N/A",
            "trailingPE": "N/A",
            "forwardPE": "N/A",
            "priceToBook": "N/A",
            "dividendYield": "N/A",
            "beta": "N/A",
            "fiftyTwoWeekHigh": "N/A",
            "fiftyTwoWeekLow": "N/A",
            "averageVolume": "N/A",
            "trailingEps": "N/A",
            "forwardEps": "N/A"
        }


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="AkShare Bridge Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port)
