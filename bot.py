import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, time, timedelta

# --- Flask Server (שומר על הבוט פעיל ב-Koyeb) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Bloomberg Bot is FULLY Operational"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- חיבור למסד הנתונים Supabase ---
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

# --- מנוע משיכת נתונים ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        meta = result['meta']
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

# --- הגדרות הבוט ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, הבוט המלא חזר לאוויר (כולל daily_on)!')
    if not alert_loop.is_running(): alert_loop.start()
    if not daily_report_loop.is_running(): daily_report_loop.start()

# --- 🔄 משימות אוטומטיות ---

@tasks.loop(minutes=5)
async def alert_loop():
    try:
        alerts = db_fetch("SELECT id, user_id, symbol, target_price, is_stoploss FROM alerts WHERE active = True")
        for a_id, u_id, sym, target, is_sl in alerts:
            d = get_data(sym)
            if d:
                triggered = (not is_sl and d['price'] >= target) or (is_sl and d['price'] <= target)
                if triggered:
                    user = await bot.fetch_user(u_id)
                    if user:
                        msg = "🚨 **התראת יעד!**" if not is_sl else "⚠️ **סטופ-לוס!**"
                        await user.send(f"{msg} {sym} הגיעה ל: **${d['price']}**")
                    db_execute("UPDATE alerts SET active = False WHERE id = %s", (a_id,))
    except Exception as e: print(f"Alert Loop Error: {e}")

@tasks.loop(time=time(hour=21, minute=30))
async def daily_report_loop():
    try:
        users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
        for (u_id,) in users:
            data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (u_id,))
            if not data: continue
            embed = discord.Embed(title="🌙 דוח לילה", color=0x2c3e50)
            for sym, shares, avg_b in data:
                d = get_data(sym)
                if d: embed.add_field(name=sym, value=f"רווח: ${(d['price']-avg_b)*shares:,.2f}", inline=False)
            user = await bot.fetch_user(u_id)
            if user: await user.send(embed=embed)
    except Exception as e: print(f"Daily Loop Error: {e}")

# --- 🏦 פקודות כסף ומזומן ---

@bot.command()
async def deposit(ctx, amount: float):
    db_execute("INSERT INTO user_balance (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = user_balance.balance + %s", (ctx.author.id, amount, amount))
    await ctx.send(f"💰 הופקדו **${amount:,.2f}** לחשבון שלך!")

@bot.command()
async def balance(ctx):
    res = db_fetch("SELECT balance FROM user_balance WHERE user_id = %s", (ctx.author.id,))
    bal = res[0][0] if res else 0
    await ctx.send(f"💵 יתרת המזומן שלך: **${bal:,.2f}**")

@bot.command()
async def buy(ctx, p_name: str, symbol: str, qty: float):
    symbol = symbol.upper()
    d = get_data(symbol)
    if not d: return await ctx.send("❌ מניה לא נמצאה.")
    cost = d['price'] * qty
    res = db_fetch("SELECT balance FROM user_balance WHERE user_id = %s", (ctx.author.id,))
    bal = res[0][0] if res else 0
    if bal < cost: return await ctx.send(f"❌ חסר כסף. עלות: ${cost:,.2f}")
    db_execute("UPDATE user_balance SET balance = balance - %s WHERE user_id = %s", (cost, ctx.author.id))
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, p_name, symbol, qty, d['price']))
    await ctx.send(f"✅ קנית {qty} {symbol}. יתרה: ${bal-cost:,.2f}")

# --- 📢 פקודות הגדרות (כאן ה-daily_on שחיפשת) ---

@bot.command()
async def daily_on(ctx):
    """הפעלת דוחות לילה אוטומטיים"""
    db_execute("INSERT INTO user_settings (user_id, daily_updates) VALUES (%s, True) ON CONFLICT (user_id) DO UPDATE SET daily_updates = True", (ctx.author.id,))
    await ctx.send("🔔 יהונתן, דוחות הלילה הופעלו! תקבל סיכום בכל ערב.")

@bot.command()
async def daily_off(ctx):
    """ביטול דוחות לילה"""
    db_execute("UPDATE user_settings SET daily_updates = False WHERE user_id = %s", (ctx.author.id,))
    await ctx.send("🔕 דוחות הלילה בוטלו.")

# --- 📊 ניתוח ומידע ---

@bot.command()
async def analyze(ctx, symbol: str):
    d = get_data(symbol)
    if not d or len(d['history']) < 14: return await ctx.send("❌ אין מספיק נתונים.")
    prices = d['history']
    gains = [max(prices[i]-prices[i-1], 0) for i in range(1, len(prices))]
    losses = [abs(min(prices[i]-prices[i-1], 0)) for i in range(1, len(prices))]
    avg_g = sum(gains[-14:])/14
    avg_l = sum(losses[-14:])/14
    rsi = 100 - (100/(1+(avg_g/avg_l if avg_l != 0 else 100)))
    status = "🔴 יקר" if rsi > 70 else "🟢 זול" if rsi < 30 else "🟡 נייטרלי"
    await ctx.send(f"🧠 {symbol.upper()} RSI: {rsi:.2f} ({status})")

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
    await ctx.send(f"🎯 התראה נקבעה ב-${price}")

@bot.command()
async def stoploss(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active, is_stoploss) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True, True))
    await ctx.send(f"⚠️ סטופ-לוס הוגדר ב-${price}")

@bot.command()
async def setup(ctx):
    ov = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True), ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    ch = await ctx.guild.create_text_channel(f"💼-{ctx.author.display_name}", overwrites=ov)
    await ctx.send(f"✅ חדר נוצר: {ch.mention}")

@bot.command()
async def help_me(ctx):
    await ctx.send("**פקודות:** `!deposit`, `!balance`, `!buy`, `!daily_on`, `!daily_off`, `!analyze`, `!stock`, `!news`, `!leaderboard`, `!alert`, `!stoploss`, `!setup`")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
