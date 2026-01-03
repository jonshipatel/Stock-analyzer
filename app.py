import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False

import numpy as np
import pandas as pd
import yfinance as yf
# Use the new google.genai package (recommended)
from google import genai   #use this for mac systems
#import google.generativeai as genai   #only for jonshi's laptop


# Initialize Firebase
#try:
  # cred = credentials.Certificate("servicekey2.json")
  
  #  cred = credentials.Certificate(
   # "servicekey2.json"
    #)
    #firebase_admin.initialize_app(cred)

    #import os
    #import json
   # import firebase_admin
  #  from firebase_admin import credentials

 #   firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
#
  #  cred = credentials.Certificate(json.loads(firebase_json))
 #   firebase_admin.initialize_app(cred)

#except ValueError:
    # App already initialized
  #  pass

# ================================
# Firebase Initialization (Render-safe)
# ================================
import json

if not firebase_admin._apps:
    try:
        firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

        if not firebase_json:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT not set")

        firebase_dict = json.loads(firebase_json)
        cred = credentials.Certificate(firebase_dict)
        firebase_admin.initialize_app(cred)

    except Exception as e:
        print("🔥 Firebase initialization failed:", e)

db = firestore.client()


# Initialize Gemini AI
#GEMINI_API_KEY = ""
import os

#API_KEY = os.environ.get("API_KEY")

#gemini_client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

#if not GEMINI_API_KEY:
 #   raise ValueError("GEMINI_API_KEY not set")

if not GEMINI_API_KEY:
    print("⚠️ GEMINI_API_KEY not set — AI features disabled")
    gemini_client = None
else:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)



# Initialize Flask
app = Flask(__name__)
if CORS_AVAILABLE:
    CORS(app)  # Enable CORS for API endpoints
def calculate_sma(series, period=14):
    return series.rolling(period).mean()

def calculate_ema(series, period=14):
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_volatility(series):
    return series.pct_change().std()

def calculate_support_resistance(series):
    return series.min(), series.max()

def analyze_stock(stock_symbol, date_from, date_to):
    try:
        df = yf.download(stock_symbol, start=date_from, end=date_to, progress=False)

        if df.empty:
            return None

        close = df["Close"]

        sma = calculate_sma(close).iloc[-1]
        ema = calculate_ema(close).iloc[-1]
        rsi = calculate_rsi(close).iloc[-1]
        volatility = calculate_volatility(close)
        support, resistance = calculate_support_resistance(close)

        trend = "Bullish" if ema > sma else "Bearish"

        if rsi < 30:
            signal = "BUY"
            risk = "Low"
        elif rsi > 70:
            signal = "SELL"
            risk = "High"
        else:
            signal = "HOLD"
            risk = "Medium"

        # OHLC for chart
        ohlc = []
        for i, row in df.iterrows():
            ohlc.append({
                "x": i.strftime("%Y-%m-%d"),
                "o": float(row["Open"]),
                "h": float(row["High"]),
                "l": float(row["Low"]),
                "c": float(row["Close"])
            })

        # Gemini explanation
        ai_explanation = None
        if gemini_client:
            prompt = f"""
Stock: {stock_symbol}
Trend: {trend}
RSI: {rsi:.1f}
Signal: {signal}
Support: {support:.2f}
Resistance: {resistance:.2f}

Explain this in 2–3 sentences for a beginner trader.
"""
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                ai_explanation = response.text
            except:
                ai_explanation = None

        return {
            "current_price": float(close.iloc[-1]),
            "sma": float(sma),
            "ema": float(ema),
            "rsi": float(rsi),
            "volatility": float(volatility),
            "volatility_percent": float(volatility * 100),
            "support": float(support),
            "resistance": float(resistance),
            "trend": trend,
            "signal": signal,
            "risk": risk,
            "momentum": "Strong" if rsi > 50 else "Weak",
            "ai_explanation": ai_explanation,
            "chart": {
                "ohlc": ohlc
            }
        }

    except Exception as e:
        print("Analysis error:", e)
        return None





@app.route('/')
def home():
    return render_template('index.html')


@app.route('/chat')
def chat():
    return render_template('chat.html')


@app.route('/analysis')
def analysis():
    return render_template('result.html')


@app.route('/add_expense', methods=['POST'])
def add_expense():
    stock_name = request.form.get('stockName')
    date_from_str = request.form.get("dateFrom")
    date_to_str = request.form.get("dateTo")
    
    if not stock_name or not date_from_str or not date_to_str:
        return render_template('index.html', error="Please fill in all fields")
    
    try:
        dateFrom = datetime.strptime(date_from_str, "%Y-%m-%d")
        dateTo = datetime.strptime(date_to_str, "%Y-%m-%d")
        
        # Save to Firebase
        db.collection("TradingData").add({
            "stockName": stock_name,
            "dateFrom": dateFrom,
            "dateTo": dateTo
        })
        
        # Redirect to analysis page with stock symbol
        return redirect(url_for('analysis', stock=stock_name, date_from=date_from_str, date_to=date_to_str))
    except Exception as e:
        return render_template('index.html', error=f"Error: {str(e)}")


@app.route('/api/analyze', methods=['GET', 'POST'])
def api_analyze():
    """API endpoint for stock analysis"""
    if request.method == 'POST':
        data = request.get_json()
        stock_symbol = data.get('stock') or request.form.get('stock')
        date_from = data.get('date_from') or request.form.get('dateFrom')
        date_to = data.get('date_to') or request.form.get('dateTo')
    else:
        stock_symbol = request.args.get('stock')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
    
    if not stock_symbol or not date_from or not date_to:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Handle Indian stocks (add .NS suffix if not present)
    if not '.' in stock_symbol:
        stock_symbol = f"{stock_symbol}.NS"
    
    result = analyze_stock(stock_symbol, date_from, date_to)
    
    if result is None:
        return jsonify({"error": "Failed to analyze stock. Please check the symbol and dates."}), 400
    
    return jsonify(result)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API endpoint for chat with Gemini AI"""
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    try:
        # Use the new google.genai API
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=message
        )
        response_text = response.text
        
        if not response_text:
            return jsonify({"error": "Empty response from AI model"}), 500
        
        return jsonify({"response": response_text})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Gemini API Error Details:\n{error_details}")
        error_msg = str(e)
        # Provide more helpful error messages
        if "API key" in error_msg.lower() or "authentication" in error_msg.lower():
            error_msg = "API key authentication failed. Please check your Gemini API key."
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            error_msg = "API quota exceeded. Please try again later."
        return jsonify({"error": f"Error generating response: {error_msg}"}), 500


#if __name__ == "__main__":              #jonshi
   # app.run(debug=True, host='0.0.0.0', port=5001)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
