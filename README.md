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

2.  Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```

3.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Server

To start the server, run:

```bash
python main.py
```

Or using uvicorn directly (for development with auto-reload):

```bash
uvicorn main:app --reload
```

The server will start at `http://127.0.0.1:8000`.

## API Endpoints

### 1. Stock History
Get historical data for a specific stock.

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
