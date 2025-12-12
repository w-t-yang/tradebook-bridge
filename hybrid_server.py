from fastapi import FastAPI, HTTPException
import yfinance as yf
from yfinance import EquityQuery
import akshare as ak
import pandas as pd
from typing import Optional
from datetime import datetime

import os

SYMBOL_TO_NAME = {}


app = FastAPI()

# 1. Root / Health Check
@app.get("/")
def read_root():
    return {"status": "ok", "server": "hybrid_server"}

def safe_float(val):
    try:
        if val is None: return None
        return float(val)
    except (ValueError, TypeError):
        return None

import json

def load_symbol_name_map():
    """Load symbol to name mapping from JSON"""
    global SYMBOL_TO_NAME
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "data", "cn_stock_names.json")
    
    if not os.path.exists(json_path):
        print(f"Warning: Name mapping JSON not found at {json_path}")
        return

    try:
        with open(json_path, mode='r', encoding='utf-8') as f:
            SYMBOL_TO_NAME = json.load(f)
                        
    except Exception as e:
        print(f"Error loading name map: {e}")

# Load on startup
load_symbol_name_map()

# --- Symbol Converters ---

def to_fixed_format(symbol: str) -> str:
    """
    Converts a symbol to the fixed format: SH/SZ + 6 digits.
    e.g. 601318 -> SH601318
    e.g. 601318.SS -> SH601318
    e.g. 000001.SZ -> SZ000001
    """
    symbol = symbol.strip().upper()
    
    # Handle yfinance format (.SS, .SZ)
    if symbol.endswith('.SS'):
        return f"SH{symbol[:-3]}"
    if symbol.endswith('.SZ'):
        return f"SZ{symbol[:-3]}"
    
    # Handle already compatible format (SH/SZ + 6 digits)
    if (symbol.startswith('SH') or symbol.startswith('SZ')) and len(symbol) == 8 and symbol[2:].isdigit():
        return symbol

    # Handle pure 6 digits
    if symbol.isdigit() and len(symbol) == 6:
        if symbol.startswith('6'):
            return f"SH{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"SZ{symbol}"
        # Beijing exchange (8, 4) might be added later, currently falling back to return as is or maybe default? 
        # User instruction implies 601318 and compatible formats. 
        # For safety, if we can't determine, just return it (or maybe default to something? No, safest is return)
        # But per requirements: "make sure it's compliant". 
        
    return symbol

def to_yfinance_format(symbol: str) -> str:
    """
    Converts a symbol to yfinance expected format.
    e.g. SH601318 -> 601318.SS
    e.g. 601318 -> 601318.SS
    """
    symbol = symbol.strip().upper()

    # If it already looks like yfinance format (checking endswith suffices for valid suffixes)
    if symbol.endswith('.SS') or symbol.endswith('.SZ'):
        return symbol

    # If it is in fixed format (SH/SZ + 6 digits)
    if len(symbol) == 8 and symbol[2:].isdigit():
        if symbol.startswith('SH'):
            return f"{symbol[2:]}.SS"
        if symbol.startswith('SZ'):
            return f"{symbol[2:]}.SZ"
            
    # If it is pure 6 digits
    if symbol.isdigit() and len(symbol) == 6:
        if symbol.startswith('6') or symbol.startswith('5'):
            return f"{symbol}.SS"
        elif symbol.startswith('0') or symbol.startswith('3') or symbol.startswith('1'):
            return f"{symbol}.SZ"
            
    return symbol


# --- Endpoints ---

# 3.1 /history (same as yfinance_server.py)
@app.get("/history")
def get_history(symbol: str, period: str = "5y", interval: str = "1d"):
    try:
        # Convert to yfinance format for fetching
        yf_symbol = to_yfinance_format(symbol)
        
        interval_mapping = {
            '1d': '1d',
            '1w': '1wk',
            '1m': '1mo',
            '1y': '3mo'
        }
        yf_interval = interval_mapping.get(interval, interval)

        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=yf_interval)
        df = df.reset_index()
        
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
             if df.empty:
                 return []
        
        df = df[required_cols]
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        
        df['date'] = df['date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else '')
        
        # Note: History items usually don't have the 'symbol' field in the array, 
        # but if we were to return it, it should be in fixed format.
        # The return type is List[Dict].
        
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3.2 /snapshot (same as akshare_server.py)
@app.get("/snapshot")
def get_snapshot():
    try:
        max_retries = 3
        df = None
        for attempt in range(max_retries):
            try:
                df = ak.stock_zh_a_spot_em()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to fetch snapshot: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to fetch market data: {str(e)}")
                import time
                time.sleep(1)
        
        if df is None:
             raise HTTPException(status_code=500, detail="Failed to fetch data")

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
        
        df = df.rename(columns=rename_map)
        
        # Ensure symbols are in fixed format
        # AkShare returns '000001' etc.
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].apply(lambda x: to_fixed_format(str(x)))

        available_cols = [col for col in rename_map.values() if col in df.columns]
        return df[available_cols].to_dict(orient="records")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3.3 /news
@app.get("/news")
def get_news(symbol: Optional[str] = None, region: str = "us"):
    region = region.lower()
    try:
        if region == "us":
            # Use yfinance
            target_symbol = to_yfinance_format(symbol) if symbol else "SPY"
            t = yf.Ticker(target_symbol)
            news = t.news
            results = []
            for n in news:
                if not n: continue
                content = n.get('content', n)
                if not content: continue
                
                title = content.get('title')
                url = content.get('clickThroughUrl', {}).get('url') if content.get('clickThroughUrl') else content.get('link')
                
                pub_date_str = ""
                if 'pubDate' in content:
                    pub_date_str = content['pubDate']
                elif 'providerPublishTime' in content:
                    pub_time = content['providerPublishTime']
                    if pub_time:
                        pub_date_str = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M:%S')
                
                summary = content.get('summary', '')
                source = content.get('provider', {}).get('displayName') if isinstance(content.get('provider'), dict) else "Yahoo Finance"
                
                results.append({
                    'publishedAt': pub_date_str,
                    'headline': title,
                    'url': url,
                    'summary': summary,
                    'source': source
                })
            return results
            
        elif region == "cn":
            # Use akshare
            if symbol:
                # AkShare expects 6 digits for stock_news_em usually
                # Convert to bare 6 digits if possible for akshare calls that require it
                # Logic: to_fixed_format gives SH123456 -> strip SH/SZ
                fixed = to_fixed_format(symbol)
                if len(fixed) == 8:
                    ak_symbol = fixed[2:]
                else:
                    ak_symbol = symbol 
                df = ak.stock_news_em(symbol=ak_symbol)
                df = df[['发布时间', '新闻标题', '新闻链接']]
                df.columns = ['publishedAt', 'headline', 'url']
                df['source'] = "East Money"
                df['summary'] = df['headline']
                return df.head(20).to_dict(orient="records")
            else:
                df = ak.stock_info_global_cls(symbol="A股24小时电报")
                # Columns: ['标题', '内容', '发布日期', '发布时间']
                # Construct datetime
                df['publishedAt'] = df['发布日期'].astype(str) + ' ' + df['发布时间'].astype(str)
                df['headline'] = df['标题'].fillna('')
                # If headline is empty, use content
                mask = df['headline'] == ''
                df.loc[mask, 'headline'] = df.loc[mask, '内容']
                
                df['summary'] = df['内容']
                df['url'] = "" # telegraphs often don't have distinct URLs
                df['source'] = "Cailian Press"
                
                df = df[['publishedAt', 'headline', 'url', 'summary', 'source']]
                return df.head(20).to_dict(orient="records")
        else:
            return []
            
    except Exception as e:
        print(f"News error: {e}")
        return []

# 3.4 /markets (yfinance)
@app.get("/markets")
def get_markets(region: str = "US"):
    indices = {}
    
    if region.upper() == "CN":
        indices = {
            '000001.SS': '上证指数',
            '399001.SZ': '深证成指',
            '000300.SS': '沪深300',
            '^HSI': '恒生指数',
            '399006.SZ': '创业板指',
            '000688.SS': '科创50',
            '000905.SS': '中证500',
            '000016.SS': '上证50'
        }
    else:
        indices = {
            '^GSPC': 'S&P 500', 
            '^DJI': 'Dow Jones', 
            '^IXIC': 'Nasdaq', 
            '^RUT': 'Russell 2000',
            '^VIX': 'VIX',
            'GC=F': 'Gold',
            'CL=F': 'Crude Oil',
            '^TNX': '10Y Treasury'
        }
    results = []
    
    for sym, name in indices.items():
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            
            price = fi.last_price
            prev_close = fi.previous_close
            
            if price is None or prev_close is None:
                continue

            change = price - prev_close
            change_percent = (change / prev_close) * 100
            
            # Use fixed format for return if it's a CN index
            display_symbol = sym
            if region.upper() == "CN":
                 # Convert to SH/SZ format for display
                 # to_fixed_format handles .SS/.SZ correctly
                 display_symbol = to_fixed_format(sym)
            
            results.append({
                'symbol': display_symbol,
                'name': name,
                'price': price,
                'change': change,
                'changePercent': change_percent,
                'prevClose': prev_close,
                'open': fi.open,
                'high': fi.day_high,
                'low': fi.day_low,
                'volume': fi.last_volume,
                'amount': 0
            })
        except Exception:
            continue
            
    return results

# 3.5 /sectors (yfinance)
@app.get("/sectors")
def get_sectors(region: str = "US"):
    sector_etfs = {}
    
    if region.upper() == "CN":
        # Domestic active sector ETFs (CSI/Other thematic) - 6 digits
        sector_etfs = {
            'Basic Materials': '512400',
            'Communication Services': '515050',
            'Consumer Cyclical': '510200',
            'Consumer Defensive': '510630',
            'Energy': '159930',
            'Financial Services': '510230',
            'Healthcare': '512170',
            'Industrials': '512660',
            'Real Estate': '512200',
            'Technology': '512760',
            'Utilities': '159985',
            'Semiconductors': '512480'
        }
    else:
        # US Sector ETFs (SPDR)
        sector_etfs = {
            'Basic Materials': 'XLB',
            'Communication Services': 'XLC',
            'Consumer Cyclical': 'XLY',
            'Consumer Defensive': 'XLP',
            'Energy': 'XLE',
            'Financial Services': 'XLF',
            'Healthcare': 'XLV',
            'Industrials': 'XLI',
            'Real Estate': 'XLRE',
            'Technology': 'XLK',
            'Utilities': 'XLU',
            'Semiconductors': 'SMH'
        }
    
    SECTOR_TRANSLATIONS = {
        'Basic Materials': '基础材料',
        'Communication Services': '通信服务',
        'Consumer Cyclical': '周期性消费',
        'Consumer Defensive': '防御性消费',
        'Energy': '能源',
        'Financial Services': '金融服务',
        'Healthcare': '医疗保健',
        'Industrials': '工业',
        'Real Estate': '房地产',
        'Technology': '科技',
        'Utilities': '公用事业',
        'Semiconductors': '半导体'
    }

    results = []
    for name, sym in sector_etfs.items():
        try:
            # For CN region, we might have pure 6 digit codes that need conversion
            # For US, they are already valid ticker symbols
            yf_sym = to_yfinance_format(sym)
            t = yf.Ticker(yf_sym)
            fi = t.fast_info
            
            price = fi.last_price
            prev_close = fi.previous_close
            
            if price is None or prev_close is None:
                continue
                
            change = price - prev_close
            change_percent = (change / prev_close) * 100
            
            display_name = name
            if region.upper() == "CN":
                display_name = SECTOR_TRANSLATIONS.get(name, name)
            
            results.append({
                'name': display_name,
                'filterKey': name,
                'change': f"{change_percent:+.2f}%",
                'isUp': change >= 0,
                'color': 'text-green-300' if change >= 0 else 'text-red-300'
            })
        except Exception:
            continue
            
    return results

# 3.6 /events (dummy)
@app.get("/events")
def get_events():
    return [
        {
            "time": "14:30",
            "country": "USA",
            "event": "CPI Data Release",
            "actual": "3.2%",
            "forecast": "3.1%",
            "impact": "High"
        },
        {
            "time": "09:30",
            "country": "CN",
            "event": "Manufacturing PMI",
            "actual": "50.1",
            "forecast": "50.0",
            "impact": "Medium"
        }
    ]

# 3.7 /info (yfinance)
def _extract_stock_info(symbol: str, info: dict) -> dict:
    yf_symbol = info.get('symbol', symbol)
    fixed_symbol = to_fixed_format(yf_symbol)
    
    return {
        "symbol": fixed_symbol,
        "name": info.get("longName") or info.get("shortName") or "N/A",
        "exchange": info.get("exchange") or "N/A",
        "currency": info.get("currency") or "N/A",
        "country": info.get("country") or "N/A",
        "sector": info.get("sector") or "N/A",
        "industry": info.get("industry") or "N/A",
        "marketCap": safe_float(info.get("marketCap")),
        "description": info.get("longBusinessSummary") or "N/A",
        "website": info.get("website") or "N/A",
        "ceo": "N/A", 
        "employees": info.get("fullTimeEmployees"),
        "founded": None,
        "ipoDate": info.get("firstTradeDateEpochUtc"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "change": info.get("regularMarketChange"),
        "changePercent": info.get("regularMarketChangePercent"),
        "trailingPE": info.get("trailingPE"),
        "forwardPE": info.get("forwardPE"),
        "priceToBook": info.get("priceToBook"),
        "dividendYield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        "averageVolume": safe_float(info.get("averageVolume")),
        "trailingEps": info.get("trailingEps"),
        "forwardEps": info.get("forwardEps")
    }

@app.get("/info/{symbol}")
def get_stock_info(symbol: str):
    try:
        # Convert to yfinance format
        yf_symbol = to_yfinance_format(symbol)
        
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        
        result = _extract_stock_info(symbol, info)
        
        # Auto-detect and map name if symbol is in our map
        sym_upper = symbol.strip().upper()
        if sym_upper in SYMBOL_TO_NAME:
            result['name'] = SYMBOL_TO_NAME[sym_upper]
        else:
            fixed = to_fixed_format(symbol)
            if fixed in SYMBOL_TO_NAME:
                result['name'] = SYMBOL_TO_NAME[fixed]
            elif len(fixed) == 8:
                 bare = fixed[2:]
                 if bare in SYMBOL_TO_NAME:
                     result['name'] = SYMBOL_TO_NAME[bare]
        
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Stock info not found: {str(e)}")
@app.get("/screener")
def get_screener_results(sector: str = "", region: str = "US"):
    try:
        valid_sector = sector.title() 
        valid_region = region.lower()
        
        try:

            if valid_sector == 'Semiconductors':
                q = EquityQuery('and', [
                    EquityQuery('eq', ['industry', 'Semiconductors']),
                    EquityQuery('eq', ['region', valid_region])
                ])
            else:
                q = EquityQuery('and', [
                    EquityQuery('eq', ['sector', valid_sector]),
                    EquityQuery('eq', ['region', valid_region])
                ]) if len(valid_sector) > 0 else EquityQuery('eq', ['region', valid_region])
            response = yf.screen(q, count=100, size=100, sortField='intradaymarketcap', sortAsc=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Screener failed: {str(e)}")
            
        if not response or 'quotes' not in response:
             return []

        results = []
        quotes = response['quotes']
        
        for quote in quotes:
            symbol = quote.get('symbol')
            if not symbol: continue
            
            stock_data = {
                "symbol": to_fixed_format(symbol), # Ensure fixed format
                "name": quote.get("longName") or quote.get("shortName") or "N/A",
                "exchange": quote.get("exchange") or "N/A",
                "currency": quote.get("currency") or "N/A",
                "country": quote.get("country") or "N/A",
                "sector": quote.get("sector") or valid_sector,
                "industry": quote.get("industry") or "N/A",
                "marketCap": safe_float(quote.get("marketCap")),
                "description": quote.get("longBusinessSummary") or "N/A",
                "website": "N/A",
                "ceo": "N/A",
                "employees": None,
                "founded": None,
                "ipoDate": quote.get("firstTradeDateMilliseconds"),
                "price": quote.get("regularMarketPrice"),
                "change": quote.get("regularMarketChange"),
                "changePercent": quote.get("regularMarketChangePercent"),
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screener error: {str(e)}")
        
    # Override names if using CN region logic (which happens inside get_screener_results via yfinance request for 'cn' region, or post-processing)
    # The current /screener implementation uses yfinance.screen(region=valid_region)
    # If region is 'cn', the symbols returned by yfinance might need name overrides from our map
    if valid_region == 'cn':
        for res in results:
            sym = res.get('symbol')
            if sym in SYMBOL_TO_NAME:
                res['name'] = SYMBOL_TO_NAME[sym]
            # Try bare symbol if not found
            if sym and len(sym) > 2 and sym[2:] in SYMBOL_TO_NAME:
                 res['name'] = SYMBOL_TO_NAME[sym[2:]]

    return results

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port)
