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

import math

def safe_float(val):
    try:
        if val is None: return None
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None

import json
import requests

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


# --- Helper for Chinese Stocks ---
def get_price_day_tx(code, end_date='', count=1250, frequency='1d'):
    """
    Fetch history from Tencent Web Interface.
    code: valid full code like 'sh600519' or 'sz000001' (lowercase prefix)
    frequency: '1d', '1w', '1m'
    """
    unit = 'week' if frequency == '1w' else 'month' if frequency == '1m' else 'day'
    
    if end_date:
        if isinstance(end_date, datetime):
            end_date = end_date.strftime('%Y-%m-%d') 
        else:
            end_date = str(end_date).split(' ')[0]
    
    # If end_date is today, clear it to get latest
    if end_date == datetime.now().strftime('%Y-%m-%d'):
        end_date = ''
        
    URL = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{unit},,{end_date},{count},qfq'
    
    # print(f"Fetching {URL}")
    resp = requests.get(URL)
    st = json.loads(resp.content)
    
    ms = 'qfq' + unit
    if code not in st['data']:
        return pd.DataFrame() # Return empty if code not found
        
    stk = st['data'][code]
    buf = stk[ms] if ms in stk else stk[unit]
    
    # Ensure we only take the first 6 columns (some stocks have 7 or more)
    buf = [item[:6] for item in buf]
    
    df = pd.DataFrame(buf, columns=['time','open','close','high','low','volume'])
    cols = ['open', 'close', 'high', 'low', 'volume']
    df[cols] = df[cols].astype(float)
    df['time'] = pd.to_datetime(df['time'])
    return df



# --- Endpoints ---

# 3.1 /history (same as yfinance_server.py)
@app.get("/history")
def get_history(symbol: str, period: str = "5y", interval: str = "1d"):
    try:
        # Convert to yfinance format for fetching
        yf_symbol = to_yfinance_format(symbol)
        
        # Check if it is a Chinese stock
        # Our to_fixed_format ensures SHxxxxxx / SZxxxxxx
        fixed_symbol = to_fixed_format(symbol)
        is_cn = fixed_symbol.startswith("SH") or fixed_symbol.startswith("SZ")
        
        if is_cn:
            # logic for Chinese stocks using get_price_day_tx
            # 1. Prepare code: 'sh600519' (lowercase)
            code = fixed_symbol.lower()
            
            # 2. Map interval
            # interval: 1d, 1w, 1m. yfinance uses 1wk, 1mo. Endpoint uses 1w, 1m (mapped inside helper to 'week', 'month')
            freq = '1d'
            if interval in ['1wk', '1w']: freq = '1w'
            if interval in ['1mo', '1m']: freq = '1m'

            # 3. Map period to count
            # approximate trading days
            period_map = {
                '1d': 1, '5d': 5, '1mo': 22, '3mo': 65, '6mo': 130, 
                '1y': 250, '2y': 500, '5y': 1250, '10y': 2500, 'max': 5000, 'ytd': 250 
            }
            # If period is not in map, try to parse it (e.g. if we get "250d" ?) - currently simple map
            count = period_map.get(period, 1250)
            
            # If period is 'ytd', we might need better handling, but count=250 is a safe fallback for "this year" roughly
            # To be precise for YTD:
            if period == 'ytd':
                start_of_year = datetime(datetime.now().year, 1, 1)
                days_diff = (datetime.now() - start_of_year).days
                # Approximate trading days (5/7)
                count = int(days_diff * 5 / 7) + 5
            
            df = get_price_day_tx(code, count=count, frequency=freq)
            
            if df.empty:
                return []

            # Format for return: [{date, open, high, low, close, volume}, ...]
            # df columns from helper: ['time','open','close','high','low','volume']
            
            results = []
            for _, row in df.iterrows():
                results.append({
                    'date': row['time'].strftime('%Y-%m-%d'),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume']
                })
            return results

        else:
            # Existing yfinance logic for non-CN stocks
            interval_mapping = {
                '1d': '1d',
                '1w': '1wk',
                '1m': '1mo',
                '1y': '3mo'
            }
            yf_interval = interval_mapping.get(interval, interval)
            # Fix weak match for 1w/1m passed from frontend if they differ
            if interval == '1w': yf_interval = '1wk'
            if interval == '1m': yf_interval = '1mo'

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
# 3.6 /events
from bs4 import BeautifulSoup

def scrape_economic_calendar():
    try:
        url = "https://www.investing.com/economic-calendar/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'id': 'economicCalendarData'})
        
        if not table:
            return []
            
        rows = table.find_all('tr')
        results = []
        current_date = ""
        
        for row in rows:
            # Date row
            if 'theDay' in row.get('class', []):
                current_date = row.get_text(strip=True)
                continue
                
            # Event row
            if 'js-event-item' in row.get('class', []):
                try:
                    time_td = row.find('td', {'class': 'time'})
                    currency_td = row.find('td', {'class': 'left flagCur'})
                    sentiment_td = row.find('td', {'class': 'sentiment'})
                    event_td = row.find('td', {'class': 'event'})
                    actual_td = row.find('td', {'class': 'act'})
                    forecast_td = row.find('td', {'class': 'fore'})
                    
                    time_str = time_td.get_text(strip=True) if time_td else ""
                    # Currency often contains formatted text, just get the code if possible
                    currency = currency_td.get_text(strip=True) if currency_td else ""
                    # Clean currency (sometimes it has newlines or spaces)
                    currency = currency.strip()
                    
                    event = event_td.get_text(strip=True) if event_td else ""
                    actual = actual_td.get_text(strip=True) if actual_td else ""
                    forecast = forecast_td.get_text(strip=True) if forecast_td else ""
                    
                    # Determine importance
                    impact = "Low"
                    if sentiment_td:
                        icons = sentiment_td.find_all('i', {'class': 'grayFullBullishIcon'})
                        if len(icons) == 3: impact = "High"
                        elif len(icons) == 2: impact = "Medium"
                        
                    results.append({
                        "date": current_date,
                        "time": time_str,
                        "country": currency, # Using currency as proxy for country/region
                        "event": event,
                        "actual": actual,
                        "forecast": forecast,
                        "impact": impact
                    })
                except Exception:
                    continue
                    
        return results
    except Exception as e:
        print(f"Scraping error: {e}")
        return []

@app.get("/events")
def get_events(impact: str = "High"):
    events = scrape_economic_calendar()
    
    # Filter based on impact if provided and not "all"
    if impact and impact.lower() != "all":
        events = [e for e in events if e.get("impact", "").lower() == impact.lower()]
        
    return events

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

# 3.8 /earnings (yfinance)
@app.get("/earnings")
def get_earnings(symbol: str):
    try:
        yf_symbol = to_yfinance_format(symbol)
        ticker = yf.Ticker(yf_symbol)
        
        # Get earnings dates (includes history and future)
        # Typically returns DataFrame with index 'Earnings Date' and columns ['EPS Estimate', 'Reported EPS', 'Surprise(%)']
        df = ticker.earnings_dates
        
        if df is None or df.empty:
            return []

        df = df.reset_index()
        results = []
        
        for _, row in df.iterrows():
            earnings_date = row.get('Earnings Date')
            if pd.isnull(earnings_date): continue
            
            # Format using safe_float
            eps_est = safe_float(row.get('EPS Estimate'))
            eps_act = safe_float(row.get('Reported EPS'))
            surprise = safe_float(row.get('Surprise(%)'))
            
            # Formatting event time (BMO/AMC) is hard from this data, sometimes it's in the timestamp
            # We'll just return the date string
            date_str = earnings_date.strftime('%Y-%m-%d %H:%M:%S')
            
            results.append({
                'date': date_str,
                'epsEstimate': eps_est,
                'epsActual': eps_act,
                'surprise': surprise,
                'year': earnings_date.year,
                'quarter': f"Q{(earnings_date.month-1)//3 + 1}" # Rough approximation if not provided
            })
            
        return results

    except Exception as e:
        print(f"Earnings fetch failed for {symbol}: {e}")
        return []
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
