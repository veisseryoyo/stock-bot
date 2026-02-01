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
def home(): return "Yoyo Ultimate Bot is Running - Full Version"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- Database Connection ---
DATABASE_URL = "postgresql://postgres:Yoyov130113!@db.ouuieanhljwxiqlljwtv.supabase.co:5432/postgres"

def db_execute(query, params):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")

def db_fetch(query, params=()):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall()
        cur.close()
        conn.close()
        return res
    except Exception as e:
        print(f"❌ Database Fetch Error: {e}")
        return []

# --- Data Fetching Engine ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        meta = result['meta']
        # מושך היסטוריית מחירים לניתוח RSI וגרפים
        history = [round(x, 2) for x in result['indicators']['quote'][0]['close'] if x is not None]
        
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
        return res['quoteSummary']['result'][0]
    except: return None

def get_news(symbol):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get('news', [])[:3]
    except: return []

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, הבוט המסיבי באוויר! (גרסת 280+ שורות)')
    if not background_loop.is_running(): background_loop.start()
    if not daily_report_loop.is_running(): daily_report_loop.start()

# --- 🔄 Tasks ---

@tasks.loop(minutes=5)
async def background_loop():
    """בדיקת התראות וסטופ-לוס"""
    alerts = db_fetch("SELECT id, user_id, symbol, target_price, is_stoploss FROM alerts WHERE active = True")
    for a_id, u_id, sym, target, is_sl in alerts:
        d = get_data(sym)
        if d:
            triggered = (not is_sl and d['price'] >= target) or (is_sl and d['price'] <= target)
            if triggered:
                user = await bot.fetch_user(u_id)
                if user:
                    msg = "🚨 **יעד מחיר הושג!**" if not is_sl else "⚠️ **סטופ-לוס הופעל!**"
                    try: await user.send(f"{msg} {sym} הגיעה ל: **${d['price']}**")
                    except: pass
                    db_execute("UPDATE alerts SET active = False WHERE id = %s", (a_id,))

@tasks.loop(time=time(hour=21, minute=30))
async def daily_report_loop():
    """דוח לילה אוטומטי"""
    users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
    for (u_id,) in users:
        data = db_fetch("SELECT portfolio_name, symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY portfolio_name, symbol", (u_id,))
        if not data: continue
        embed = discord.Embed(title="🌙 סיכום יום מסחר", color=0x2c3e50)
        total_pnl = 0
        for p_name, sym, shares, avg_b in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_b) * shares
                total_pnl += pnl
                embed.add_field(name=f"[{p_name}] {sym}", value=f"רווח: ${pnl:,.2f}", inline=False)
        embed.description = f"**סה''כ רווח יומי: ${total_pnl:,.2f}**"
        user = await bot.fetch_user(u_id)
        if user: await user.send(embed=embed)

# --- 🏦 פקודות בנקאות ומזומן ---

@bot.command()
async def deposit(ctx, amount: float):
    db_execute("INSERT INTO user_balance (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = user_balance.balance + %s", (ctx.author.id, amount, amount))
    await ctx.send(f"💰 יהונתן, הפקדת **${amount:,.2f}** למזומן!")

@bot.command()
async def balance(ctx):
    res = db_fetch("SELECT balance FROM user_balance WHERE user_id = %s", (ctx.author.id,))
    bal = res[0][0] if res else 0
    await ctx.send(f"💵 יתרת המזומן שלך: **${bal:,.2f}**")

# --- 💼 ניהול תיקים וקניות ---

@bot.command()
async def create_p(ctx, name: str):
    await ctx.send(f"✅ תיק **{name}** הוגדר במערכת!")

@bot.command()
async def buy(ctx, p_name: str, symbol: str, qty: float):
    symbol = symbol.upper()
    d = get_data(symbol)
    if not d: return await ctx.send("❌ מניה לא קיימת.")
    cost = d['price'] * qty
    res = db_fetch("SELECT balance FROM user_balance WHERE user_id = %s", (ctx.author.id,))
    bal = res[0][0] if res else 0
    if bal < cost: return await ctx.send(f"❌ חסר כסף! עלות: ${cost:,.2f}, יתרה: ${bal:,.2f}")
    db_execute("UPDATE user_balance SET balance = balance - %s WHERE user_id = %s", (cost, ctx.author.id))
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, p_name, symbol, qty, d['price']))
    await ctx.send(f"✅ קנית {qty} {symbol} לתיק {p_name}. יתרה חדשה: **${bal-cost:,.2f}**")

@bot.command()
async def add(ctx, p_name: str, symbol: str, qty: float, price: float = 0):
    symbol = symbol.upper()
    if price == 0:
        d = get_data(symbol)
        price = d['price'] if d else 0
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, p_name, symbol, qty, price))
    await ctx.send(f"✅ נוסף ידנית: {qty} {symbol} לתיק {p_name}.")

@bot.command()
async def my_p(ctx, p_name: str = None):
    q = "SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s"
    p = [ctx.author.id]
    if p_name: q += " AND portfolio_name = %s GROUP BY symbol"; p.append(p_name)
    else: q += " GROUP BY symbol"
    rows = db_fetch(q, tuple(p))
    if not rows: return await ctx.send("📪 אין נכסים.")
    embed = discord.Embed(title=f"💼 תיק: {p_name if p_name else 'כללי'}", color=0x3498db)
    for s, q, b in rows:
        d = get_data(s)
        if d: embed.add_field(name=s, value=f"{q} יחידות | שווי: ${q*d['price']:,.2f}", inline=False)
    await ctx.send(embed=embed)

# --- 🧠 פקודות ניתוח שוק ---

@bot.command()
async def analyze(ctx, symbol: str):
    d = get_data(symbol)
    if not d or len(d['history']) < 14: return await ctx.send("❌ חסר דאטה.")
    prices = d['history']
    gains = [max(prices[i]-prices[i-1], 0) for i in range(1, len(prices))]
    losses = [abs(min(prices[i]-prices[i-1], 0)) for i in range(1, len(prices))]
    avg_g = sum(gains[-14:])/14
    avg_l = sum(losses[-14:])/14
    rsi = 100 - (100/(1+(avg_g/avg_l if avg_l != 0 else 100)))
    status = "🔴 יקר מאוד" if rsi > 70 else "🟢 הזדמנות קנייה" if rsi < 30 else "🟡 יציב"
    await ctx.send(f"🧠 **ניתוח {symbol.upper()}**: RSI {rsi:.2f} ({status})")

@bot.command()
async def stock(ctx, symbol: str):
    d = get_data(symbol)
    if d:
        chart = f"https://quickchart.io/chart?c={{type:'line',data:{{labels:[1,2,3,4,5],datasets:[{{label:'{symbol.upper()}',data:{d['history'][-5:]},borderColor:'green'}}]}}}}"
        e = discord.Embed(title=f"📊 {symbol.upper()}", color=0x2ecc71)
        e.add_field(name="מחיר", value=f"${d['price']}"); e.set_image(url=chart)
        await ctx.send(embed=e)

@bot.command()
async def news(ctx, symbol: str):
    n = get_news(symbol)
    e = discord.Embed(title=f"📰 חדשות {symbol.upper()}", color=0xf1c40f)
    for a in n: e.add_field(name=a['title'], value=f"[לינק]({a['link']})", inline=False)
    await ctx.send(embed=e)

@bot.command()
async def dividends(ctx, symbol: str):
    s = get_full_stats(symbol)
    if not s: return await ctx.send("אין נתונים.")
    rate = s['summaryDetail'].get('dividendRate', {}).get('fmt', '0')
    await ctx.send(f"💰 {symbol.upper()} מחלקת: ${rate} למניה.")

# --- 🏆 תחרויות ועזרים ---

@bot.command()
async def leaderboard(ctx):
    users = db_fetch("SELECT DISTINCT user_id FROM portfolios")
    ranks = []
    for (u_id,) in users:
        p_data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (u_id,))
        pnl = sum((get_data(s)['price'] - b)*q for s,q,b in p_data if get_data(s))
        u = await bot.fetch_user(u_id)
        ranks.append((u.display_name if u else str(u_id), pnl))
    ranks.sort(key=lambda x: x[1], reverse=True)
    e = discord.Embed(title="🏆 מובילי הרווחים", color=0xf1c40f)
    for i, (n, p) in enumerate(ranks[:5], 1): e.add_field(name=f"{i}. {n}", value=f"${p:,.2f}", inline=False)
    await ctx.send(embed=e)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active, is_stoploss) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True, False))
    await ctx.send(f"🎯 התראה נקבעה ל-{symbol.upper()} ב-${price}")

@bot.command()
async def stoploss(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active, is_stoploss) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True, True))
    await ctx.send(f"⚠️ סטופ-לוס הוגדר ל-{symbol.upper()} ב-${price}")

@bot.command()
async def copy(ctx, user: discord.Member, p_name: str):
    data = db_fetch("SELECT symbol, shares, buy_price FROM portfolios WHERE user_id = %s AND portfolio_name = %s", (user.id, p_name))
    for s, q, p in data:
        db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, f"Copy_{p_name}", s, q, p))
    await ctx.send(f"✅ התיק הועתק מ-{user.display_name}")

@bot.command()
async def risk(ctx):
    d = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    total = sum(r[1] for r in d)
    e = discord.Embed(title="⚠️ ניתוח חשיפה", color=0xe74c3c)
    for s, v in d: e.add_field(name=s, value=f"{(v/total)*100:.1f}%")
    await ctx.send(embed=e)

@bot.command()
async def setup(ctx):
    ov = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True), ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    ch = await ctx.guild.create_text_channel(f"💼-{ctx.author.display_name}", overwrites=ov)
    await ctx.send(f"✅ חדר נוצר: {ch.mention}")

@bot.command()
async def help_me(ctx):
    await ctx.send("**פקודות:** `!deposit`, `!balance`, `!buy`, `!add`, `!my_p`, `!analyze`, `!stock`, `!news`, `!dividends`, `!leaderboard`, `!alert`, `!stoploss`, `!copy`, `!risk`, `!setup`")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
