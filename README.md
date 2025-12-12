# Tradebook Data Server

This directory contains Python servers using FastAPI to provide stock market data for the Tradebook application.

## Prerequisites

-   Python 3.8+
-   [Poetry](https://python-poetry.org/docs/#installation) (Dependency Manager)

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

### Hybrid Server (Recommended)
Combines data from **yfinance** (US/Global) and **AkShare** (China A-Shares).
Automatic symbol conversion is handled (e.g., `601318` -> `SH601318`).

```bash
poetry run python hybrid_server.py --port 8000
# Or with auto-reload
poetry run uvicorn hybrid_server:app --reload --port 8000
```

### Other Servers (For Reference)
You can explore these to understand how individual data providers are implemented.

-   **yfinance_server.py**: US/Global market data only.
-   **akshare_server.py**: Chinese A-Share market data only.

## API Endpoints (Hybrid Server)

### 1. Stock History
Get historical price data.
-   **URL:** `/history`
-   **Method:** `GET`
-   **Parameters:**
    -   `symbol` (required): Stock symbol.
    -   `period` (optional): Data period (default: "5y").
    -   `interval` (optional): Data interval (default: "1d").

### 2. Market Snapshot
Get real-time data for Chinese A-Shares (via AkShare).
-   **URL:** `/snapshot`
-   **Method:** `GET`

### 3. News
Get news for specific stock or market.
-   **URL:** `/news`
-   **Method:** `GET`
-   **Parameters:**
    -   `symbol` (optional): Stock symbol.
    -   `region` (optional): `us` (default) for Yahoo Finance news, `cn` for East Money news.

### 4. Markets & Sectors
-   `/markets`: Major US/Global Indices.
-   `/sectors`: US Sector Performance.

### 5. Stock Info
-   **URL:** `/info/{symbol}`
-   **Method:** `GET`
-   **Description:** Get detailed stock information.
-   **Auto-Detection:** If the symbol is identified as a Chinese stock (present in the server's name map), the `name` field will be automatically localized to Chinese.

### 6. Other
-   `/screener`
-   `/events`
