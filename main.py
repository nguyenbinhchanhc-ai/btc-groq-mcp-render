import os
import sys
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Try importing from the installed tradingview-mcp-server package first.
# If not installed, fallback to the local clone path.
try:
    import tradingview_mcp
except ImportError:
    # Resolve the local clone path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_mcp_path = os.path.join(parent_dir, "tradingview-mcp", "src")
    if os.path.exists(local_mcp_path):
        sys.path.append(local_mcp_path)
    try:
        import tradingview_mcp
    except ImportError as e:
        print(f"Error: tradingview_mcp library could not be imported. Detail: {e}")

from tradingview_mcp.core.services.screener_service import analyze_coin
from tradingview_mcp.core.services.yahoo_finance_service import get_price
from tradingview_mcp.core.services.news_service import fetch_news

load_dotenv()

app = FastAPI(title="BTC Groq MCP Analytics Server")

# Mount frontend static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/quote")
async def get_market_quote(symbol: str = "BTC-USD"):
    """
    Get live quote from Yahoo Finance (used for initial/quick page loads).
    Does not require a Groq API Key.
    """
    price_data = get_price(symbol)
    if "error" in price_data:
        return {"error": price_data["error"]}
    return price_data

class AnalyzeRequest(BaseModel):
    pass

@app.post("/api/analyze")
async def run_analysis(
    symbol: str = "BTCUSDT",
    exchange: str = "BINANCE",
    timeframe: str = "1h",
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
    x_groq_model: Optional[str] = Header(None, alias="X-Groq-Model")
):
    """
    1. Fetch live BTC prices from Yahoo Finance (BTC-USD)
    2. Get technical analysis indicators from TradingView MCP (BTCUSDT)
    3. Retrieve recent news headlines from crypto feeds
    4. Compile data and send to Groq AI for an expert trading recommendation
    """
    # Determine the Groq API key (Header first, then Env Var)
    api_key = x_groq_api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Groq API Key is missing. Please save it in settings or set GROQ_API_KEY environment variable on the server."
        )

    # Determine Groq Model
    model = x_groq_model or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"

    try:
        # Step 1: Yahoo price
        price_details = get_price("BTC-USD")
        
        # Step 2: TradingView analysis
        # Note: analyze_coin expects the basic symbol and exchange name
        tv_details = analyze_coin(symbol, exchange, timeframe)
        if "error" in tv_details:
            raise Exception(f"TradingView analysis failed: {tv_details['error']}")
            
        # Step 3: News
        news_details = fetch_news(symbol="BTC", category="crypto", limit=5)
        
        # Step 4: AI Analysis using Groq
        ai_verdict = analyze_with_groq(api_key, model, price_details, tv_details, news_details)
        
        return {
            "price_details": price_details,
            "technical_details": tv_details,
            "news_details": news_details,
            "ai_analysis": ai_verdict
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def analyze_with_groq(api_key: str, model: str, price: dict, tv: dict, news: list) -> dict:
    """
    Call Groq API using the OpenAI library configured for Groq
    """
    from openai import OpenAI
    import json

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key
    )

    # Prepare data details for the prompt
    price_info = f"""
Current price: {price.get('price')} USD
Change 24h: {price.get('change_pct')}% ({price.get('change')} USD)
52W High: {price.get('52w_high')}, 52W Low: {price.get('52w_low')}
"""

    rsi_val = tv.get("rsi", {}).get("rsi", "N/A")
    macd_val = tv.get("macd", {}).get("macd", 0)
    macd_sig = tv.get("macd", {}).get("signal", 0)
    bb_upper = tv.get("bollinger_bands", {}).get("upper", 0)
    bb_lower = tv.get("bollinger_bands", {}).get("lower", 0)
    overall_rating = tv.get("market_sentiment", {}).get("overall_rating", 0)
    overall_signal = tv.get("market_sentiment", {}).get("buy_sell_signal", "NEUTRAL")

    technical_info = f"""
TradingView Signals (Interval: {tv.get('timeframe')}):
- RSI (14): {rsi_val}
- MACD Line: {macd_val:.4f}, MACD Signal: {macd_sig:.4f} (Crossover: {'BULLISH' if macd_val > macd_sig else 'BEARISH'})
- Bollinger Bands: Upper {bb_upper:.2f}, Lower {bb_lower:.2f}
- Overall Technical Rating: {overall_rating} (Signal: {overall_signal})
- Volume analysis: {tv.get('volume_analysis', {})}
- ADX trend strength: {tv.get('adx', {}).get('adx', 'N/A')}
- Support/Resistance: {tv.get('support_resistance', {})}
"""

    news_info = ""
    for idx, item in enumerate(news):
        news_info += f"- [{item.get('source')}] {item.get('title')} ({item.get('published')})\n"
    if not news_info:
        news_info = "No recent headlines available."

    system_prompt = """
You are a professional cryptocurrency research and trading intelligence system.
Your job is to analyze the technical metrics from TradingView, current prices, and news, and formulate a clear, actionable trading thesis.
You MUST write all text descriptions, reasoning, and bullet points in Vietnamese.
You must return your output strictly in JSON format.
The JSON must contain exactly these keys:
{
  "decision": "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
  "confidence": <integer between 0 and 100>,
  "reasoning": "<Tóm tắt nhận định bằng tiếng Việt (2-3 câu)>",
  "bullish_thesis_points": [
    "<Luận điểm tăng giá 1 bằng tiếng Việt>",
    "<Luận điểm tăng giá 2 bằng tiếng Việt>",
    "<Luận điểm tăng giá 3 bằng tiếng Việt>"
  ],
  "bearish_thesis_points": [
    "<Luận điểm giảm giá 1 bằng tiếng Việt>",
    "<Luận điểm giảm giá 2 bằng tiếng Việt>",
    "<Luận điểm giảm giá 3 bằng tiếng Việt>"
  ]
}
"""

    user_prompt = f"""
Please analyze this market data for Bitcoin:

[Market Price Data]
{price_info}

[Technical Analysis Data]
{technical_info}

[Recent News Headlines]
{news_info}
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.25,
        response_format={"type": "json_object"}
    )

    try:
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        # Fallback in case of JSON parse error
        return {
            "decision": "HOLD",
            "confidence": 50,
            "reasoning": f"Failed to parse Groq response: {str(e)}",
            "bullish_thesis_points": ["Could not extract"],
            "bearish_thesis_points": ["Could not extract"]
        }
