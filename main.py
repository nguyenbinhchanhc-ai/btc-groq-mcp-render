# Monkey patch requests to bypass TradingView Cloudflare blocks on Render (datacenter IPs)
import requests
original_post = requests.post
def custom_post(url, *args, **kwargs):
    headers = kwargs.get("headers", {})
    if "tradingview.com" in url:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        kwargs["headers"] = headers
    return original_post(url, *args, **kwargs)
requests.post = custom_post
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

@app.get("/api/technicals")
async def get_technical_data(
    symbol: str = "BTCUSDT",
    exchange: str = "BINANCE",
    timeframe: str = "1h"
):
    """
    Get only price details and technical indicators from TradingView MCP.
    Does not run Groq AI, suitable for lightweight periodic polling.
    """
    try:
        price_details = get_price("BTC-USD")
        tv_details = analyze_coin(symbol, exchange, timeframe)
        if "error" in tv_details:
            return {"error": tv_details["error"]}
        return {
            "price_details": price_details,
            "technical_details": tv_details
        }
    except Exception as e:
        return {"error": str(e)}

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
    # Safe check in case parameter helpers are passed directly in python calls
    api_key = x_groq_api_key
    if not isinstance(api_key, str) and hasattr(api_key, "default"):
        api_key = None
    
    api_key = api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Groq API Key is missing. Please save it in settings or set GROQ_API_KEY environment variable on the server."
        )

    # Determine Groq Model safely
    model = x_groq_model
    if not isinstance(model, str) and hasattr(model, "default"):
        model = None
    model = model or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"

    try:
        # Step 1: Yahoo price
        price_details = get_price("BTC-USD")
        
        # Step 2: TradingView analysis
        # Note: analyze_coin expects the basic symbol and exchange name
        tv_details = analyze_coin(symbol, exchange, timeframe)
        if "error" in tv_details:
            raise Exception(f"TradingView analysis failed: {tv_details['error']}")
            
        # Step 3: News (run asynchronously in executor with a 3.0s timeout to prevent blocking ASGI event loop)
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            news_details = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: fetch_news(symbol="BTC", category="crypto", limit=5)),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            news_details = []
        
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

    current_price = price.get("price") or 60000.0
    sr = tv.get("support_resistance") or {}
    pivot = sr.get("pivot") or current_price
    r1 = sr.get("resistance_1") or (current_price + 500)
    r2 = sr.get("resistance_2") or (current_price + 1000)
    s1 = sr.get("support_1") or (current_price - 500)
    s2 = sr.get("support_2") or (current_price - 1000)
    
    # Safe guard ATR volatility to ensure it is never None or 0
    atr_val = tv.get("atr") or {}
    atr_val = atr_val.get("value")
    if atr_val is None or atr_val == 0:
        atr_val = 300.0

    # Prepare data details for the prompt
    price_info = f"""
Current price: {current_price} USD
Change 24h: {price.get('change_pct')}% ({price.get('change')} USD)
52W High: {price.get('52w_high')}, 52W Low: {price.get('52w_low')}
"""

    rsi_val = tv.get("rsi", {}).get("value", "N/A")
    macd_val = tv.get("macd", {}).get("macd_line", 0)
    macd_sig = tv.get("macd", {}).get("signal_line", 0)
    bb_upper = tv.get("bollinger_bands", {}).get("upper", 0)
    bb_lower = tv.get("bollinger_bands", {}).get("lower", 0)
    overall_rating = tv.get("market_sentiment", {}).get("overall_rating", 0)
    overall_signal = tv.get("market_sentiment", {}).get("buy_sell_signal", "NEUTRAL")

    technical_info = f"""
TradingView Signals (Interval: {tv.get('timeframe')}):
- RSI (14): {rsi_val}
- MACD Line: {macd_val:.6f}, MACD Signal: {macd_sig:.4f} (Crossover: {'BULLISH' if macd_val > macd_sig else 'BEARISH'})
- Bollinger Bands: Upper {bb_upper:.2f}, Lower {bb_lower:.2f}
- Overall Technical Rating: {overall_rating} (Signal: {overall_signal})
- Volume analysis: {tv.get('volume_analysis', {})}
- ADX trend strength: {tv.get('adx', {}).get('value', 'N/A')} ({tv.get('adx', {}).get('trend_strength', 'N/A')})
- Stochastic: {tv.get('stochastic', {})}
- Support/Resistance: {sr}
"""

    news_info = ""
    for idx, item in enumerate(news):
        news_info += f"- [{item.get('source')}] {item.get('title')} ({item.get('published')})\n"
    if not news_info:
        news_info = "No recent headlines available."

    system_prompt = """
You are a professional cryptocurrency research and trading intelligence system.
Your job is to analyze the technical metrics from TradingView, current prices, and news, and formulate a clear, mathematical trading thesis.
You MUST write all text descriptions, reasoning, and bullet points in Vietnamese.
You must return your output strictly in JSON format.

CRITICAL INSTRUCTIONS FOR PROBABILITY CALCULATION:
- Do NOT output rounded probabilities (like 70%, 80%, or 50% unless it is a perfect tie).
- Calculate a precise composite probability score for bullish vs bearish based on:
  * RSI (value vs 50 baseline): weight 20%
  * MACD Crossover state and trend: weight 20%
  * ADX trend strength (value + DI comparison): weight 15%
  * Stochastic Oscillator: weight 15%
  * Bollinger Bands width and price position: weight 15%
  * SMA/EMA trend alignment: weight 15%
- The probabilities MUST fluctuate granularly (e.g. 61% vs 39%, 56% vs 44%, 48% vs 52%, etc.) reflecting the minor real-time ticks of indicators.
- The probability percentage for the dominant side must be between 40% and 100%.

CRITICAL INSTRUCTION FOR TIMEFRAME COUNTDOWN:
- Calculate the target countdown minutes (target_timeframe_minutes) using the formula: (abs(target_price - current_price) / ATR) * 60 minutes.
- Return this prediction in the 'target_timeframe_minutes' key as an exact integer. Do not make it static (e.g. do not just return 90).
- Also return a friendly text representation in the 'target_timeframe' key (e.g. "trong vòng 45 phút", "trong 3 giờ tới").

The JSON must contain exactly these keys:
{
  "decision": "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
  "confidence": <integer between 0 and 100>,
  "probability_bullish": <integer representing probability percentage of upward movement, e.g., 61>,
  "probability_bearish": <integer representing probability percentage of downward movement, e.g., 39 (sum must equal 100)>,
  "target_price": <float representing specific target price BTC will run to next>,
  "target_timeframe": "<string representing expected time>",
  "target_timeframe_minutes": <integer representing minutes to target for the live countdown>,
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

[CRITICAL MATHEMATICAL CONSTRAINTS]
- CURRENT PRICE OF BTC IS: {current_price} USD.
- SUPPORT LEVELS: S1={s1}, S2={s2}. RESISTANCE LEVELS: R1={r1}, R2={r2}.
- ATR VOLATILITY: {atr_val} USD.
- DO NOT copy the examples in the system prompt instructions.
- CẤM TUYỆT ĐỐI không được trả về giá trị trùng khít hoàn toàn với các mức R1={r1}, R2={r2}, S1={s1}, S2={s2} hay Pivot={pivot}.
- Target Price (target_price) phải là một số lẻ thập phân cụ thể di động liên tục theo giá hiện tại (ví dụ: {current_price + 314.50} hoặc {current_price - 245.20} dựa trên tín hiệu).
- Nếu bạn đoán xu hướng TĂNG (BULLISH), hãy chọn target_price lớn hơn {current_price} nhưng nhỏ hơn {r2}.
- Nếu bạn đoán xu hướng GIẢM (BEARISH), hãy chọn target_price nhỏ hơn {current_price} nhưng lớn hơn {s2}.
- Số target_price này phải thay đổi linh hoạt theo từng yêu cầu chứ không được cố định một mức duy nhất.
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
        result = json.loads(content)
        
        # Calculate target_timeframe and target_timeframe_minutes programmatically
        # to ensure 100% mathematical accuracy based on current price & ATR
        try:
            t_price = float(result.get("target_price") or current_price)
            price_diff = abs(t_price - current_price)
            
            tf = tv.get("timeframe") or "1h"
            tf_factor = 60.0 # minutes per candle
            if tf == "15m":
                tf_factor = 15.0
            elif tf == "4h":
                tf_factor = 240.0
            elif tf == "1D":
                tf_factor = 1440.0
                
            if atr_val and atr_val > 0:
                expected_mins = (price_diff / atr_val) * tf_factor
            else:
                expected_mins = 60.0
                
            target_minutes = int(round(expected_mins))
            if target_minutes < 15:
                target_minutes = 15 # minimum reasonable bound
                
            result["target_timeframe_minutes"] = target_minutes
            
            # Format friendly Vietnamese string
            hrs = target_minutes // 60
            mins = target_minutes % 60
            if hrs > 0:
                result["target_timeframe"] = f"khoảng {hrs} giờ {mins} phút" if mins > 0 else f"khoảng {hrs} giờ"
            else:
                result["target_timeframe"] = f"khoảng {mins} phút"
        except Exception:
            result["target_timeframe_minutes"] = 120
            result["target_timeframe"] = "khoảng 2 giờ"
            
        # Calculate probability_bullish and probability_bearish programmatically
        # to ensure 100% mathematical responsiveness to real-time indicators
        try:
            rsi_val = tv.get("rsi", {}).get("value")
            if rsi_val is None:
                rsi_val = 50.0
            rsi_contrib = rsi_val / 100.0
            
            macd = tv.get("macd", {})
            macd_line = macd.get("macd_line") or 0.0
            signal_line = macd.get("signal_line") or 0.0
            macd_contrib = 0.75 if macd_line > signal_line else 0.25
            
            p_val = current_price
            ema20 = tv.get("ema", {}).get("ema20") or p_val
            sma50 = tv.get("sma", {}).get("sma50") or p_val
            sma200 = tv.get("sma", {}).get("sma200") or p_val
            
            trend_score = 0
            if p_val > ema20: trend_score += 1
            if p_val > sma50: trend_score += 1
            if p_val > sma200: trend_score += 1
            trend_contrib = trend_score / 3.0
            
            stoch = tv.get("stochastic", {})
            k_val = stoch.get("k") or 50.0
            stoch_contrib = k_val / 100.0
            
            sentiment = tv.get("market_sentiment", {})
            sig = sentiment.get("buy_sell_signal") or "NEUTRAL"
            if "BUY" in sig:
                sent_contrib = 0.8
            elif "SELL" in sig:
                sent_contrib = 0.2
            else:
                sent_contrib = 0.5
                
            bullish_score = (
                rsi_contrib * 0.25 +
                macd_contrib * 0.25 +
                trend_contrib * 0.20 +
                stoch_contrib * 0.15 +
                sent_contrib * 0.15
            )
            
            import random
            noise = random.uniform(-1.5, 1.5)
            prob_bull = int(round(40.0 + bullish_score * 55.0 + noise))
            prob_bull = max(40, min(95, prob_bull))
            prob_bear = 100 - prob_bull
            
            result["probability_bullish"] = prob_bull
            result["probability_bearish"] = prob_bear
            
        except Exception:
            result["probability_bullish"] = 55
            result["probability_bearish"] = 45
            
        return result
    except Exception as e:
        # Fallback in case of JSON parse error
        return {
            "decision": "HOLD",
            "confidence": 50,
            "probability_bullish": 50,
            "probability_bearish": 50,
            "target_price": price.get("price", 60000.0),
            "target_timeframe": "Không xác định",
            "target_timeframe_minutes": 120,
            "reasoning": f"Lỗi phân tích phản hồi Groq: {str(e)}",
            "bullish_thesis_points": ["Không thể trích xuất"],
            "bearish_thesis_points": ["Không thể trích xuất"]
        }
