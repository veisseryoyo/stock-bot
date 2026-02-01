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

# --- מנוע משיכת נתונים (מניות, קריפטו, היסטוריה וסטטיסטיקה) ---
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

# --- הגדרות הבוט ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, הבוט המלא באוויר ללא קיצורים!')
    if not alert_loop.is_running(): alert_loop.start()
    if not daily_report_loop.is_running(): daily_report_loop.start()

# --- 🔄 מערכות אוטומטיות (Tasks) ---

@tasks.loop(minutes=5)
async def alert_loop():
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for a_id, u_id, sym, target in alerts:
        d = get_data(sym)
        if d and d['price'] >= target:
            user = await bot.fetch_user(u_id)
            if user:
                try:
                    await user.send(f"🚨 **התראת מחיר ליהונתן!** {sym} הגיעה ליעד: **${d['price']}**")
                except: pass
                db_execute("UPDATE alerts SET active = False WHERE id = %s", (a_id,))

@tasks.loop(time=time(hour=21, minute=30)) # 23:30 שעון ישראל
async def daily_report_loop():
    users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
    for (u_id,) in users:
        data = db_fetch("SELECT portfolio_name, symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY portfolio_name, symbol", (u_id,))
        if not data: continue
        embed = discord.Embed(title="🌙 דוח סוף יום מסחר", color=0x2c3e50, timestamp=datetime.now())
        for p_name, sym, shares, avg_b in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_b) * shares
                embed.add_field(name=f"[{p_name}] {sym}", value=f"מחיר: ${d['price']} | רווח/הפסד: ${pnl:,.2f}", inline=False)
        user = await bot.fetch_user(u_id)
        if user: await user.send(embed=embed)

# --- 💼 פקודות ניהול תיקים מרובים ---

@bot.command()
async def create_p(ctx, name: str):
    await ctx.send(f"✅ תיק בשם **{name}** נוצר. עכשיו תוכל להוסיף אליו מניות.")

@bot.command()
async def list_p(ctx):
    data = db_fetch("SELECT DISTINCT portfolio_name FROM portfolios WHERE user_id = %s", (ctx.author.id,))
    if not data: return await ctx.send("📪 אין לך תיקים עדיין.")
    names = "\n".join([f"• {row[0]}" for row in data])
    await ctx.send(f"📂 **התיקים שלך:**\n{names}")

@bot.command()
async def add(ctx, p_name: str, symbol: str, qty: float, price: float = 0):
    symbol = symbol.upper()
    if price == 0:
        d = get_data(symbol)
        if d: price = d['price']
        else: return await ctx.send("❌ לא מצאתי מחיר שוק.")
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", 
               (ctx.author.id, p_name, symbol, qty, price))
    await ctx.send(f"✅ נוסף לתיק {p_name}: **{qty}** יחידות של {symbol} ב מחיר **${price:,.2f}**")

@bot.command()
async def my_p(ctx, p_name: str = None):
    query = "SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s"
    params = [ctx.author.id]
    if p_name: query += " AND portfolio_name = %s GROUP BY symbol"; params.append(p_name)
    else: query += " GROUP BY symbol"
    
    rows = db_fetch(query, tuple(params))
    if not rows: return await ctx.send("📪 התיק ריק.")
    embed = discord.Embed(title=f"💼 תיק: {p_name if p_name else 'כללי'}", color=0x3498db)
    total = 0
    for s, q, b in rows:
        d = get_data(s)
        if d:
            val = q * d['price']
            total += val
            embed.add_field(name=s, value=f"כמות: {q} | שווי: ${val:,.2f} | רווח: ${(d['price']-b)*q:,.2f}", inline=False)
    embed.set_footer(text=f"שווי כולל: ${total:,.2f}")
    await ctx.send(embed=embed)

# --- 🧠 פקודות ניתוח חכם (RSI, Top, News, Dividends) ---

@bot.command()
async def analyze(ctx, symbol: str):
    d = get_data(symbol)
    if not d or len(d['history']) < 14: return await ctx.send("❌ אין מספיק נתונים לניתוח.")
    prices = d['history']
    gains = [max(prices[i] - prices[i-1], 0) for i in range(1, len(prices))]
    losses = [abs(min(prices[i] - prices[i-1], 0)) for i in range(1, len(prices))]
    avg_g = sum(gains[-14:]) / 14
    avg_l = sum(losses[-14:]) / 14
    rsi = 100 - (100 / (1 + (avg_g / avg_l if avg_l != 0 else 100)))
    status = "🔴 קניית יתר (יקר)" if rsi > 70 else "🟢 מכירת יתר (זול)" if rsi < 30 else "🟡 נייטרלי"
    await ctx.send(f"🧠 ניתוח {symbol.upper()}: RSI הוא **{rsi:.2f}**. מצב: **{status}**")

@bot.command()
async def top(ctx):
    watch = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "GOOGL"]
    embed = discord.Embed(title="🔥 המזיזות של השוק", color=0xe67e22)
    for s in watch:
        d = get_data(s)
        if d: embed.add_field(name=s, value=f"${d['price']} ({d['change']:.2f}%)", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def news(ctx, symbol: str):
    articles = get_news(symbol)
    if not articles: return await ctx.send("אין חדשות.")
    embed = discord.Embed(title=f"📰 חדשות: {symbol.upper()}", color=0xf1c40f)
    for a in articles: embed.add_field(name=a['title'], value=f"[לינק]({a['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def dividends(ctx, symbol: str):
    s = get_full_stats(symbol)
    if not s: return await ctx.send("אין נתונים.")
    rate = s['summaryDetail'].get('dividendRate', {}).get('fmt', '0')
    date = s['summaryDetail'].get('exDividendDate', {}).get('fmt', 'N/A')
    await ctx.send(f"💰 {symbol.upper()}: דיבידנד שנתי ${rate} | תאריך קרוב: {date}")

# --- 🛠️ פקודות עזר והתראות ---

@bot.command()
async def alert(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 התראה נקבעה ל-{symbol.upper()} ב-${price}")

@bot.command()
async def copy(ctx, user: discord.Member, p_name: str):
    data = db_fetch("SELECT symbol, shares, buy_price FROM portfolios WHERE user_id = %s AND portfolio_name = %s", (user.id, p_name))
    if not data: return await ctx.send("התיק לא נמצא.")
    for s, q, p in data:
        db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", (ctx.author.id, f"Copy_{p_name}", s, q, p))
    await ctx.send(f"✅ התיק של {user.display_name} הועתק!")

@bot.command()
async def risk(ctx):
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("אין נתונים.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח חשיפה", color=0xe74c3c)
    for s, v in data: embed.add_field(name=s, value=f"{(v/total)*100:.1f}% מהתיק")
    await ctx.send(embed=embed)

@bot.command()
async def setup(ctx):
    overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True), ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    channel = await ctx.guild.create_text_channel(f"💼-{ctx.author.display_name}", overwrites=overwrites)
    await ctx.send(f"✅ חדר נוצר: {channel.mention}")

@bot.command()
async def help_me(ctx):
    msg = """**🤖 פקודות בוט yoyo:**
`!create_p`, `!list_p`, `!add`, `!my_p`, `!analyze`, `!top`, `!news`, `!dividends`, `!alert`, `!copy`, `!risk`, `!setup`"""
    await ctx.send(msg)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
