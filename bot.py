import discord
from discord.ext import commands, tasks
import requests
import os
import sqlite3
import urllib.parse
from flask import Flask
from threading import Thread

# --- הגדרת Flask עבור Koyeb (Health Check) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- ניהול מסד נתונים (SQLite) ---
def init_db():
    conn = sqlite3.connect('stocks_bot.db')
    c = conn.cursor()
    # טבלה לתיק השקעות
    c.execute('''CREATE TABLE IF NOT EXISTS portfolios 
                 (user_id INTEGER, symbol TEXT, shares INTEGER)''')
    # טבלה להתראות מחיר
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (user_id INTEGER, symbol TEXT, target_price REAL)''')
    conn.commit()
    conn.close()

def db_execute(query, params):
    conn = sqlite3.connect('stocks_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_fetch(query, params=()):
    conn = sqlite3.connect('stocks_bot.db')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall()
    conn.close()
    return res

# --- פונקציות עזר למניות ---
def get_stock_details(symbol):
    # משתמשים ב-Yahoo Finance (או Finnhub לפי הצורך)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=7d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        price = result['meta']['regularMarketPrice']
        prev_close = result['meta']['chartPreviousClose']
        change = ((price - prev_close) / prev_close) * 100
        history = [round(x, 2) for x in result['indicators']['quote'][0]['close'] if x is not None]
        return {"price": round(price, 2), "change": round(change, 2), "history": history}
    except: return None

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    init_db()
    if not check_alerts.is_running():
        check_alerts.start()
    print(f'✅ הבוט של {bot.user.name} מחובר עם מסד נתונים!')

# --- פקודות חדשות ---

@bot.command()
async def add(ctx, symbol: str, shares: int):
    """הוספת מניות לתיק האישי במסד הנתונים"""
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (?, ?, ?)", 
               (ctx.author.id, symbol, shares))
    await ctx.send(f"✅ יהונתן, הוספתי {shares} מניות של {symbol} לתיק השמור שלך!")

@bot.command()
async def my_p(ctx):
    """הצגת התיק השמור מהמסד"""
    data = db_fetch("SELECT symbol, SUM(shares) FROM portfolios WHERE user_id = ? GROUP BY symbol", (ctx.author.id,))
    if not data:
        await ctx.send("📪 התיק שלך ריק. השתמש ב-`!add` כדי להוסיף מניות.")
        return
    
    embed = discord.Embed(title=f"💼 התיק של {ctx.author.display_name}", color=0x3498db)
    total_val = 0
    for sym, shares in data:
        d = get_stock_details(sym)
        if d:
            v = d['price'] * shares
            total_val += v
            embed.add_field(name=f"{sym} ({shares} יחידות)", value=f"מחיר: ${d['price']} | שווי: ${v:,.2f}", inline=False)
    
    embed.add_field(name='💰 שווי כולל', value=f'**${total_val:,.2f}**', inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    """הוספת התראת מחיר"""
    symbol = symbol.upper()
    db_execute("INSERT INTO alerts (user_id, symbol, target_price) VALUES (?, ?, ?)", 
               (ctx.author.id, symbol, price))
    await ctx.send(f"🔔 קלטתי! אני אעדכן אותך כש-{symbol} תגיע ל-${price}.")

@tasks.loop(minutes=10)
async def check_alerts():
    """בדיקה אוטומטית של התראות"""
    alerts = db_fetch("SELECT user_id, symbol, target_price FROM alerts")
    for uid, sym, target in alerts:
        d = get_stock_details(sym)
        if d and d['price'] >= target:
            user = await bot.fetch_user(uid)
            await user.send(f"🚀 **התראה!** המניה {sym} הגיעה למחיר היעד שלך: ${d['price']} (יעד: ${target})")
            db_execute("DELETE FROM alerts WHERE user_id = ? AND symbol = ?", (uid, sym))

@bot.command()
async def stock(ctx, symbol: str):
    """פקודת המניה המקורית עם הגרף והתיקון"""
    data = get_stock_details(symbol)
    if data:
        symbol = symbol.upper()
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol}',data:{data['history']},borderColor:'green',fill:false}}]}}}}"
        encoded_config = urllib.parse.quote(chart_config)
        chart_url = f"https://quickchart.io/chart?c={encoded_config}"
        
        embed = discord.Embed(title=f"📊 מניית {symbol}", color=0x2ecc71)
        embed.add_field(name="💰 מחיר", value=f"${data['price']}", inline=True)
        embed.add_field(name="📈 שינוי", value=f"{data['change']:.2f}%", inline=True)
        embed.set_image(url=chart_url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ לא מצאתי נתונים עבור {symbol}")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
