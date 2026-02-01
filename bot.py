import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, time, timedelta

# --- Flask Server (Keep Alive) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Bloomberg Bot is FULLY Active"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- Database Connection ---
DATABASE_URL = "postgresql://postgres:Yoyov130113!@db.ouuieanhljwxiqlljwtv.supabase.co:5432/postgres"

def db_execute(query, params):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

def db_fetch(query, params=()):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# --- Data Fetching Engine ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        
        hist_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"
        hist_res = requests.get(hist_url, headers=headers).json()
        history = [round(x, 2) for x in hist_res['chart']['result'][0]['indicators']['quote'][0]['close'] if x is not None]
        
        return {
            "price": round(meta['regularMarketPrice'], 2),
            "prev": meta['chartPreviousClose'],
            "change": ((meta['regularMarketPrice'] - meta['chartPreviousClose']) / meta['chartPreviousClose']) * 100,
            "history": history,
            "currency": meta.get('currency', 'USD')
        }
    except: return None

def get_full_stats(symbol):
    url = f"https://query1.finance.yahoo.com/v11/finance/quoteSummary/{symbol.upper()}?modules=summaryDetail,defaultKeyStatistics"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        data = res['quoteSummary']['result'][0]
        return data
    except: return None

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, כל המערכות פועלות! הבוט הכי מתקדם שלך באוויר.')
    if not background_tasks.is_running(): background_tasks.start()

# --- Tasks ---
@tasks.loop(minutes=10)
async def background_tasks():
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        d = get_data(symbol)
        if d and d['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel: await channel.send(f"🚨 **יהונתן, יעד הושג!** {symbol} חצתה את ${target}")
                    db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

# --- NEW: Smart Analysis (RSI) ---
@bot.command()
async def analyze(ctx, symbol: str):
    """מנתח אם המניה בקניית יתר או מכירת יתר"""
    d = get_data(symbol)
    if not d or len(d['history']) < 14: return await ctx.send("❌ אין מספיק נתונים לניתוח.")
    
    prices = d['history']
    gains = []
    losses = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    
    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14
    if avg_loss == 0: rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    status = "🔴 קניית יתר (יקר)" if rsi > 70 else "🟢 מכירת יתר (זול)" if rsi < 30 else "🟡 נייטרלי"
    embed = discord.Embed(title=f"🧠 ניתוח חכם: {symbol.upper()}", color=0x3498db)
    embed.add_field(name="מדד RSI (14 יום)", value=f"{rsi:.2f}", inline=True)
    embed.add_field(name="מצב שוק", value=status, inline=True)
    embed.set_footer(text="ניתוח זה אינו המלצה פיננסית")
    await ctx.send(embed=embed)

# --- NEW: Top Movers ---
@bot.command()
async def top(ctx):
    """מציג את המניות החמות ביותר כרגע"""
    watch_list = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "GOOGL", "META", "AMD"]
    movers = []
    for s in watch_list:
        d = get_data(s)
        if d: movers.append((s, d['change']))
    
    movers.sort(key=lambda x: x[1], reverse=True)
    embed = discord.Embed(title="🔥 המניות החמות של היום", color=0xe67e22)
    for s, c in movers:
        emoji = "🚀" if c > 0 else "📉"
        embed.add_field(name=s, value=f"{emoji} {c:.2f}%", inline=True)
    await ctx.send(embed=embed)

# --- NEW: Dividends Tracker ---
@bot.command()
async def dividends(ctx, symbol: str):
    """בודק מתי חלוקת הדיבידנד הבאה"""
    stats = get_full_stats(symbol)
    if not stats: return await ctx.send("❌ לא נמצאו נתונים.")
    
    div_rate = stats['summaryDetail'].get('dividendRate', {}).get('fmt', 'N/A')
    div_date = stats['summaryDetail'].get('exDividendDate', {}).get('fmt', 'N/A')
    
    embed = discord.Embed(title=f"💰 דיבידנדים: {symbol.upper()}", color=0x2ecc71)
    embed.add_field(name="גובה דיבידנד (שנתי)", value=f"${div_rate}", inline=True)
    embed.add_field(name="תאריך ה-Ex-Dividend", value=div_date, inline=True)
    await ctx.send(embed=embed)

# --- NEW: Copy Portfolio ---
@bot.command()
async def copy(ctx, user_to_copy: discord.Member, portfolio_name: str):
    """מעתיק תיק של משתמש אחר לתוך תיק חדש שלך"""
    data = db_fetch("SELECT symbol, shares, buy_price FROM portfolios WHERE user_id = %s AND portfolio_name = %s", (user_to_copy.id, portfolio_name))
    if not data: return await ctx.send(f"❌ לא מצאתי תיק בשם {portfolio_name} אצל {user_to_copy.display_name}")
    
    new_p_name = f"Copied_{portfolio_name}"
    for sym, shares, price in data:
        db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", 
                   (ctx.author.id, new_p_name, sym, shares, price))
    
    await ctx.send(f"✅ יהונתן, העתקתי את התיק של {user_to_copy.display_name} לתיק חדש אצלך בשם **{new_p_name}**!")

# --- Core Portfolio Management ---

@bot.command()
async def create_p(ctx, name: str):
    await ctx.send(f"✅ תיק **{name}** נוצר. השתמש ב-`!add {name} SYM QTY` כדי למלא אותו.")

@bot.command()
async def add(ctx, p_name: str, symbol: str, qty: float, price: float = 0):
    symbol = symbol.upper()
    if price == 0:
        d = get_data(symbol)
        price = d['price'] if d else 0
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, p_name, symbol, qty, price))
    await ctx.send(f"✅ הוספתי {qty} {symbol} לתיק {p_name}.")

@bot.command()
async def my_p(ctx, p_name: str = None):
    q = "SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s"
    p = [ctx.author.id]
    if p_name:
        q += " AND portfolio_name = %s GROUP BY symbol"; p.append(p_name)
    else: q += " GROUP BY symbol"
    
    rows = db_fetch(q, tuple(p))
    if not rows: return await ctx.send("📪 תיק ריק.")
    
    embed = discord.Embed(title=f"💼 תיק השקעות", color=0x9b59b6)
    total = 0
    for s, q, b in rows:
        d = get_data(s)
        if d:
            curr_val = q * d['price']
            total += curr_val
            embed.add_field(name=s, value=f"כמות: {q} | שווי: ${curr_val:,.2f}", inline=False)
    embed.set_footer(text=f"שווי כולל: ${total:,.2f}")
    await ctx.send(embed=embed)

@bot.command()
async def stock(ctx, symbol: str):
    d = get_data(symbol)
    if d:
        chart = f"https://quickchart.io/chart?c={{type:'line',data:{{labels:[1,2,3,4,5],datasets:[{{label:'{symbol.upper()}',data:{d['history'][-5:]},borderColor:'blue'}}]}}}}"
        e = discord.Embed(title=f"📊 {symbol.upper()}", color=0x2ecc71)
        e.add_field(name="מחיר", value=f"${d['price']}"); e.set_image(url=chart)
        await ctx.send(embed=e)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 התראה נקבעה ל-{symbol.upper()} ב-${price}")

@bot.command()
async def help_me(ctx):
    m = """**🤖 פקודות ה-VIP של יהונתן:**
`!analyze [SYM]` - ניתוח חכם (RSI)
`!top` - המניות הכי חזקות היום
`!dividends [SYM]` - מתי תקבל כסף
`!copy [@USER] [P_NAME]` - העתקת תיקים
`!create_p [NAME]` | `!add [P_NAME] [SYM] [QTY]`
`!my_p (P_NAME)` | `!stock [SYM]` | `!alert [SYM] [PRICE]`"""
    await ctx.send(m)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
