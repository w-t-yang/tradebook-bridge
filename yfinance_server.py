from fastapi import FastAPI, HTTPException
import yfinance as yf
import pandas as pd
from typing import Optional
from datetime import datetime

app = FastAPI()

# 1. Root / Health Check
@app.get("/")
def read_root():
    return {"status": "ok", "server": "yfinance_bridge"}

def convert_symbol(symbol: str) -> str:
    """
    Convert stock symbol to yfinance format.
    Handles Chinese stock symbols (SH/SZ prefix or 6-digit code).
    """
    # Check for SH/SZ prefix (e.g., SH000001, SZ000001)
    if symbol.startswith('SH') and len(symbol) == 8 and symbol[2:].isdigit():
        return f"{symbol[2:]}.SS"
    elif symbol.startswith('SZ') and len(symbol) == 8 and symbol[2:].isdigit():
        return f"{symbol[2:]}.SZ"
    # Check for 6-digit Chinese symbols
    elif symbol.isdigit() and len(symbol) == 6:
        if symbol.startswith('6'):
            return f"{symbol}.SS"
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"{symbol}.SZ"
        # Add more rules here if needed (e.g., Beijing Stock Exchange)
    
    return symbol

# 1. Stock Data (History)
@app.get("/history")
def get_history(symbol: str, period: str = "5y", interval: str = "1d"):
    try:
        # Map custom intervals to yfinance intervals
        interval_mapping = {
            '1d': '1d',
            '1w': '1wk',
            '1m': '1mo',
            '1y': '3mo'
        }
        yf_interval = interval_mapping.get(interval, interval)

        yf_interval = interval_mapping.get(interval, interval)

        # Handle Chinese stock symbols
        symbol = convert_symbol(symbol)

        # yfinance period options: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=yf_interval)
        df = df.reset_index()
        
        # Ensure columns exist (yfinance returns Capital Case)
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
             # Try to handle case where data might be empty or different format
             if df.empty:
                 return []
        
        df = df[required_cols]
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        
        # Convert Timestamp to string
        df['date'] = df['date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else '')
        
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Screener (Market Snapshot)
@app.get("/snapshot")
def get_snapshot():
    # Demo: Fetch data for a few popular US stocks to simulate a screener/snapshot
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'AMD', 'INTC']
    results = []
    
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            
            # fast_info provides quick access to latest price data
            price = fi.last_price
            prev_close = fi.previous_close
            
            if price is None or prev_close is None:
                continue
                
            change = price - prev_close
            change_percent = (change / prev_close) * 100
            
            results.append({
                'symbol': sym,
                'name': sym, # fast_info doesn't provide full name easily without extra request
                'price': price,
                'change': change,
                'changePercent': change_percent,
                'volume': fi.last_volume,
                'amount': fi.last_volume * price, # Approximate amount
                'prevClose': prev_close,
                'open': fi.open,
                'high': fi.day_high,
                'low': fi.day_low
            })
        except Exception:
            continue
            
    return results

# 3. News
@app.get("/news")
def get_news(symbol: Optional[str] = None):
    target_symbol = convert_symbol(symbol) if symbol else "SPY" # Default to S&P 500 if no symbol
    try:
        t = yf.Ticker(target_symbol)
        news = t.news
        results = []
        for n in news:
            if not n:
                continue
                
            # yfinance news items structure can vary
            # Try to extract from 'content' if available
            content = n.get('content', n)
            
            if not content:
                continue
            
            title = content.get('title')
            url = content.get('clickThroughUrl', {}).get('url') if content.get('clickThroughUrl') else None
            if not url:
                url = content.get('link')
                
            pub_date_str = ""
            if 'pubDate' in content:
                pub_date_str = content['pubDate'] # Often already a string
            elif 'providerPublishTime' in content:
                pub_time = content['providerPublishTime']
                if pub_time:
                    pub_date_str = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M:%S')
                
            # Extract summary and source
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Market Status / Indices
@app.get("/markets")
def get_markets():
    # Major US Indices
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
            
            results.append({
                'symbol': sym,
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

# 5. Sectors Performance
@app.get("/sectors")
def get_sectors():
    # Use Sector ETFs as proxies
    sector_etfs = {
        'Technology': 'XLK',
        'Financials': 'XLF',
        'Healthcare': 'XLV',
        'Energy': 'XLE',
        'Materials': 'XLB',
        'Real Estate': 'XLRE',
        'Industrials': 'XLI',
        'Utilities': 'XLU',
        'Consumer Disc': 'XLY',
        'Consumer Staples': 'XLP',
        'Communication': 'XLC'
    }
    
    results = []
    for name, sym in sector_etfs.items():
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            
            price = fi.last_price
            prev_close = fi.previous_close
            
            if price is None or prev_close is None:
                continue
                
            change = price - prev_close
            change_percent = (change / prev_close) * 100
            
            results.append({
                'name': name,
                'filterKey': name, # Used for filtering news/stocks
                'change': f"{change_percent:+.2f}%",
                'isUp': change >= 0,
                'color': 'text-green-500' if change >= 0 else 'text-red-500'
            })
        except Exception:
            continue
            
    return results

# 6. Market Events (Mock)
@app.get("/events")
def get_events():
    # yfinance doesn't provide a good economic calendar API
    # Return some mock events for now to populate the UI
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
            "time": "16:00",
            "country": "USA",
            "event": "Fed Interest Rate Decision",
            "actual": "-",
            "forecast": "5.50%",
            "impact": "High"
        },
        {
            "time": "09:30",
            "country": "EUR",
            "event": "ECB Press Conference",
            "actual": "-",
            "forecast": "-",
            "impact": "Medium"
        }
    ]

# Stock Info Endpoint
@app.get("/info/{symbol}")
def get_stock_info(symbol: str):
    try:
        # Handle Chinese stock symbols
        original_symbol = symbol
        symbol = convert_symbol(symbol)
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Extract relevant fields, use "N/A" for missing data
        return {
            "symbol": original_symbol,
            "name": info.get("longName") or info.get("shortName") or "N/A",
            "exchange": info.get("exchange") or "N/A",
            "currency": info.get("currency") or "N/A",
            "country": info.get("country") or "N/A",
            "sector": info.get("sector") or "N/A",
            "industry": info.get("industry") or "N/A",
            "marketCap": str(info.get("marketCap", "N/A")),
            "description": info.get("longBusinessSummary") or "N/A",
            "website": info.get("website") or "N/A",
            "ceo": "N/A",  # yfinance doesn't provide CEO info directly
            "employees": info.get("fullTimeEmployees"),
            "founded": None,  # yfinance doesn't provide founding year
            "ipoDate": info.get("firstTradeDateEpochUtc")
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Stock info not found: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="YFinance Bridge Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port)
