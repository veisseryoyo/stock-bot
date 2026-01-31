import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread

# --- Flask ל-Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "Pro Bot Online"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- חיבור למסד הנתונים ---
def get_db_connection():
    return psycopg2.connect("postgresql://postgres:Yoyov130113!@db.ouuieanhljwxiqlljwtv.supabase.co:5432/postgres")

def db_execute(query, params):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

def db_fetch(query, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# --- פונקציות נתונים (מניות + קריפטו + חדשות) ---
def get_data(symbol):
    # תמיכה גם בקריפטו (למשל BTC-USD) וגם במניות
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL"]: sym += "-USD"
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        meta = res['chart']['result'][0]['meta']
        return {"price": round(meta['regularMarketPrice'], 2), "prev": meta['chartPreviousClose']}
    except: return None

def get_news(symbol):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        return res['news'][:3] # מחזיר 3 חדשות אחרונות
    except: return []

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def add(ctx, symbol: str, shares: int, price: float):
    """פקודה חדשה: !add [מניה] [כמות] [מחיר קנייה]"""
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol, shares, price))
    await ctx.send(f"✅ שמרתי {shares} מניות של {symbol} במחיר קנייה של ${price}")

@bot.command()
async def my_p(ctx):
    """תיק השקעות כולל חישובי רווח והפסד (PNL)"""
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data:
        return await ctx.send("📪 התיק ריק.")
    
    embed = discord.Embed(title="💼 תיק ההשקעות המורחב של יהונתן", color=0x3498db)
    total_invested = 0
    total_current = 0

    for sym, shares, avg_buy in data:
        current = get_data(sym)
        if current:
            invested = shares * avg_buy
            current_val = shares * current['price']
            profit = current_val - invested
            perc = (profit / invested) * 100 if invested > 0 else 0
            
            total_invested += invested
            total_current += current_val
            
            status = "📈" if profit >= 0 else "📉"
            embed.add_field(
                name=f"{status} {sym} ({shares} יחידות)",
                value=f"שווי: ${current_val:,.2f}\nרווח/הפסד: ${profit:,.2f} ({perc:.2f}%)",
                inline=False
            )

    total_profit = total_current - total_invested
    embed.set_footer(text=f"סה''כ שווי תיק: ${total_current:,.2f} | רווח כולל: ${total_profit:,.2f}")
    await ctx.send(embed=embed)

@bot.command()
async def news(ctx, symbol: str):
    """הבאת חדשות אחרונות על מניה או קריפטו"""
    articles = get_news(symbol)
    if not articles:
        return await ctx.send(f"❌ לא מצאתי חדשות עבור {symbol}")
    
    embed = discord.Embed(title=f"📰 חדשות חמות: {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לקריאה נוספת]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def crypto(ctx, symbol: str):
    """בדיקת מחיר קריפטו מהיר (BTC, ETH, SOL)"""
    data = get_data(symbol)
    if data:
        await ctx.send(f"🪙 מחיר ה-{symbol.upper()} הוא כרגע: **${data['price']:,}**")
    else:
        await ctx.send("❌ מטבע לא נמצא.")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
