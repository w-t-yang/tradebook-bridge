# Tradebook Data Server

This is a simple Python server using FastAPI and AkShare to provide stock market data for the Tradebook application.

## Prerequisites

- Python 3.8+
- pip

## Installation

1.  Navigate to the `server` directory:
    ```bash
    cd server
    ```

2.  Install dependencies using Poetry:
    ```bash
    poetry install
    ```

## Running the Server

You can run either the AkShare-based server (Chinese Market) or the YFinance-based server (US/Global Market).

### Option 1: AkShare Server (Chinese Market)
Runs on port 8000.

```bash
poetry run python akshare_server.py
# Or with auto-reload
poetry run uvicorn akshare_server:app --reload --port 8000
```

### Option 2: YFinance Server (US/Global Market)
Runs on port 8001.

```bash
poetry run python yfinance_server.py
# Or with auto-reload
poetry run uvicorn yfinance_server:app --reload --port 8001
```

## API Endpoints

Both servers provide consistent endpoints:


-   **URL:** `/history`
-   **Method:** `GET`
-   **Parameters:**
    -   `symbol` (required): Stock symbol (e.g., "600519").
    -   `period` (optional): Data period (default: "daily").
-   **Example:** `http://127.0.0.1:8000/history?symbol=600519`

### 2. Market Snapshot (Screener)
Get real-time data for all stocks.

-   **URL:** `/snapshot`
-   **Method:** `GET`
-   **Example:** `http://127.0.0.1:8000/snapshot`

### 3. News
Get news for a specific stock or general market news.

-   **URL:** `/news`
-   **Method:** `GET`
-   **Parameters:**
    -   `symbol` (optional): Stock symbol. If omitted, returns general market news.
-   **Example:** `http://127.0.0.1:8000/news?symbol=600519`

### 4. Market Indices
Get data for major market indices.

-   **URL:** `/markets`
-   **Method:** `GET`
-   **Example:** `http://127.0.0.1:8000/markets`
