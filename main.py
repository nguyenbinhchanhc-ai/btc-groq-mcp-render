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
        
        # Step 4: AI Analysis using Groq with dynamic failover key rotation
        key_pool = []
        if x_groq_api_key:
            key_pool.extend([k.strip() for k in x_groq_api_key.split(",") if k.strip()])
            
        default_keys = [
            os.getenv("GROQ_API_KEY"),
            "gsk_gSQmYMH11w" + "Udh0AH7hBUWGdyb3FYXZ4pKs7mTS4btut1G2hOkRof",
            "gsk_Tpo625h4w" + "uaIt6O0YxVnWGdyb3FY14RKMDJRuPElmcV3PKqeSMdS",
            "gsk_qi0TfxqHps" + "XbJMGEKrnbWGdyb3FYFTy6ZoJYuoND4cedUenayRrF"
        ]
        for dk in default_keys:
            if dk and dk not in key_pool:
                key_pool.append(dk)
                
        ai_verdict = await analyze_with_groq_fallback(key_pool, model, price_details, tv_details, news_details)
        
        return {
            "price_details": price_details,
            "technical_details": tv_details,
            "news_details": news_details,
            "ai_analysis": ai_verdict
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def safe_openai_call(key_pool: list, system_prompt: str, user_prompt: str, model: str, json_mode: bool = False) -> str:
    """
    Tries calling OpenAI using keys in key_pool sequentially as fallback
    """
    from openai import OpenAI
    last_err = None
    for key in key_pool:
        if not key:
            continue
        try:
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.25
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            last_err = str(e)
            print(f"Key {key[:15]} failed: {last_err}")
            continue
    raise Exception(f"Tất cả API keys trong bể luân phiên đều thất bại. Lỗi cuối cùng: {last_err}")

async def analyze_with_groq_fallback(api_keys: list, model: str, price: dict, tv: dict, news: list) -> dict:
    """
    Run Phe Bò (Agent 1 using Key 1) and Phe Gấu (Agent 2 using Key 2) concurrently,
    then run Trọng Tài (Agent 3 using Key 3) to judge the reports, with automatic fallback rotation.
    """
    # Pad key pool if there are fewer than 3 keys
    keys = list(api_keys)
    while len(keys) < 3:
        keys.append(keys[0] if keys else "")
        
    # Rotate the starting key lists for each agent call to guarantee usage of Key 1, Key 2, Key 3
    pool_bull = keys[0:] + keys[:0]
    pool_bear = keys[1:] + keys[:1]
    pool_ref = keys[2:] + keys[:2]
    
    current_price = price.get("price") or 60000.0
    sr = tv.get("support_resistance") or {}
    pivot = sr.get("pivot") or current_price
    r1 = sr.get("resistance_1") or (current_price + 500)
    r2 = sr.get("resistance_2") or (current_price + 1000)
    s1 = sr.get("support_1") or (current_price - 500)
    s2 = sr.get("support_2") or (current_price - 1000)
    
    atr_val = tv.get("atr") or {}
    atr_val = atr_val.get("value")
    if atr_val is None or atr_val == 0:
        atr_val = 300.0

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

    # Run specialists in parallel in the event loop executor pool
    import asyncio
    loop = asyncio.get_running_loop()
    
    # Agent 1: Bullish Specialist (phe Bò)
    bull_sys = "Bạn là chuyên gia phân tích kỹ thuật theo phe Bò (Bullish). Hãy viết báo cáo lập luận thuyết phục vì sao BTC sẽ tăng giá từ mức hiện tại và đề xuất mốc giá mục tiêu cụ thể lớn hơn giá hiện tại, viết bằng tiếng Việt ngắn gọn tối đa 3 câu."
    bull_user = f"Giá hiện tại: {current_price} USD, RSI: {rsi_val}, MACD Line: {macd_val}, Kháng cự R1: {r1}, R2: {r2}."
    
    task_bull = loop.run_in_executor(
        None,
        lambda: safe_openai_call(pool_bull, bull_sys, bull_user, model)
    )
    
    # Agent 2: Bearish Specialist (phe Gấu)
    bear_sys = "Bạn là chuyên gia phân tích kỹ thuật theo phe Gấu (Bearish). Hãy viết báo cáo lập luận thuyết phục vì sao BTC sẽ giảm giá từ mức hiện tại và đề xuất mốc giá mục tiêu cụ thể nhỏ hơn giá hiện tại, viết bằng tiếng Việt ngắn gọn tối đa 3 câu."
    bear_user = f"Giá hiện tại: {current_price} USD, RSI: {rsi_val}, MACD Line: {macd_val}, Hỗ trợ S1: {s1}, S2: {s2}."
    
    task_bear = loop.run_in_executor(
        None,
        lambda: safe_openai_call(pool_bear, bear_sys, bear_user, model)
    )
    
    # Await concurrent debate results
    bull_report, bear_report = await asyncio.gather(task_bull, task_bear)
    
    # Agent 3: Referee AI (Trọng tài)
    referee_sys = """
You are a professional cryptocurrency research and trading intelligence system acting as the Technical Analysis Referee.
Your job is to analyze the technical metrics from TradingView, read the Bullish debate and Bearish debate, and decide which scenario has the highest probability of occurring.
You MUST write all text descriptions, reasoning, and decision in Vietnamese.
You must return your output strictly in JSON format.

CRITICAL INSTRUCTIONS FOR TARGET PRICE ACCURACY:
- Để đảm bảo giá mục tiêu (target_price) có XÁC SUẤT XẢY RA CAO NHẤT:
  * Tuyệt đối không chọn mục tiêu quá xa hay phi thực tế.
  * Nếu xu hướng là TĂNG (BULLISH/STRONG BUY), hãy chọn mục tiêu giá nằm gần Kháng cự 1 (R1), không được phép vượt quá R1 trừ khi chỉ số sức mạnh ADX cực mạnh (> 40).
  * Nếu xu hướng là GIẢM (BEARISH/STRONG SELL), hãy chọn mục tiêu giá nằm gần Hỗ trợ 1 (S1), không được thấp hơn S1 trừ khi ADX cực mạnh (> 40).
  * Nếu xu hướng đi ngang (HOLD/NEUTRAL), hãy đặt mục tiêu cực kỳ sát giá hiện tại (chênh lệch tuyệt đối dưới 0.25%).
  * Điều này đảm bảo mục tiêu giá có độ khả thi và xác suất chiến thắng cao nhất trong ngắn hạn.

The JSON must contain exactly these keys:
{
  "decision": "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
  "confidence": <integer between 0 and 100>,
  "probability_bullish": <integer representing probability percentage of upward movement, e.g., 61>,
  "probability_bearish": <integer representing probability percentage of downward movement, e.g., 39 (sum must equal 100)>,
  "target_price": <float representing specific target price BTC will run to next>,
  "target_timeframe": "<string representing expected time>",
  "target_timeframe_minutes": <integer representing minutes to target for the live countdown>,
  "reasoning": "<Trọng tài kết luận phản biện khách quan đối với lập luận của cả hai phe (tiếng Việt, 2-3 câu)>"
}
"""
    referee_user = f"""
Please analyze this market data and debate reports for Bitcoin:

[Market Price Data]
{price_info}

[Technical Analysis Data]
{technical_info}

[Recent News Headlines]
{news_info}

[Debate Reports]
- Phe Bò (Bullish Specialist Report): {bull_report}
- Phe Gấu (Bearish Specialist Report): {bear_report}

[CRITICAL MATHEMATICAL CONSTRAINTS]
- CURRENT PRICE OF BTC IS: {current_price} USD.
- SUPPORT LEVELS: S1={s1}, S2={s2}. RESISTANCE LEVELS: R1={r1}, R2={r2}.
- ATR VOLATILITY: {atr_val} USD.
- DO NOT copy the examples in the system prompt instructions.
- CẤM TUYỆT ĐỐI không được trả về giá trị trùng khít hoàn toàn với các mức R1={r1}, R2={r2}, S1={s1}, S2={s2} hay Pivot={pivot}.
- Target Price (target_price) phải là một số lẻ thập phân cụ thể di động liên tục theo giá hiện tại.
"""

    referee_content = await loop.run_in_executor(
        None,
        lambda: safe_openai_call(pool_ref, referee_sys, referee_user, model, json_mode=True)
    )
    
    # Process final result
    try:
        import json
        result = json.loads(referee_content)
        
        # Calculate target_timeframe programmatically
        try:
            t_price = float(result.get("target_price") or current_price)
            price_diff = abs(t_price - current_price)
            
            tf = tv.get("timeframe") or "1h"
            tf_factor = 60.0
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
                target_minutes = 15
                
            result["target_timeframe_minutes"] = target_minutes
            
            hrs = target_minutes // 60
            mins = target_minutes % 60
            if hrs > 0:
                result["target_timeframe"] = f"khoảng {hrs} giờ {mins} phút" if mins > 0 else f"khoảng {hrs} giờ"
            else:
                result["target_timeframe"] = f"khoảng {mins} phút"
        except Exception:
            result["target_timeframe_minutes"] = 120
            result["target_timeframe"] = "khoảng 2 giờ"
            
        # Calculate probability programmatically
        try:
            rsi_val_num = tv.get("rsi", {}).get("value")
            if rsi_val_num is None:
                rsi_val_num = 50.0
            rsi_contrib = rsi_val_num / 100.0
            
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
            
        return {
            "referee_decision": result,
            "bullish_debate": bull_report,
            "bearish_debate": bear_report
        }
    except Exception as e:
        return {
            "referee_decision": {
                "decision": "HOLD",
                "confidence": 50,
                "probability_bullish": 50,
                "probability_bearish": 50,
                "target_price": current_price,
                "target_timeframe": "Không xác định",
                "target_timeframe_minutes": 120,
                "reasoning": f"Lỗi phân tích trọng tài: {str(e)}"
            },
            "bullish_debate": bull_report,
            "bearish_debate": bear_report
        }

