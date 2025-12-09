from fastapi import FastAPI, HTTPException
import yfinance as yf
import pandas as pd
from typing import Optional
from datetime import datetime

app = FastAPI()

# 1. Stock Data (History)
@app.get("/history")
def get_history(symbol: str, period: str = "1mo"):
    try:
        # yfinance period options: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
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
    target_symbol = symbol if symbol else "SPY" # Default to S&P 500 if no symbol
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
                
            results.append({
                'publishedAt': pub_date_str,
                'headline': title,
                'url': url
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
        '^RUT': 'Russell 2000'
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001) # Run on port 8001 to avoid conflict if both are running
