import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, time

# --- Flask Server (Keep Alive for Koyeb) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Stock Bot is Fully Operational"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- Database Connection (Supabase) ---
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
        
        hist_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=7d&interval=1d"
        hist_res = requests.get(hist_url, headers=headers).json()
        history = [round(x, 2) for x in hist_res['chart']['result'][0]['indicators']['quote'][0]['close'] if x is not None]
        
        return {
            "price": round(meta['regularMarketPrice'], 2),
            "prev": meta['chartPreviousClose'],
            "change": ((meta['regularMarketPrice'] - meta['chartPreviousClose']) / meta['chartPreviousClose']) * 100,
            "history": history,
            "name": meta.get('symbol', sym)
        }
    except: return None

def get_news(symbol):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get('news', [])[:3]
    except: return []

# --- Bot Initialization ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט המלא של יהונתן באוויר!')
    if not background_loop.is_running():
        background_loop.start()
    if not daily_report_task.is_running():
        daily_report_task.start()

# --- 🔄 Tasks: Alerts & Daily Reports ---

@tasks.loop(minutes=5)
async def background_loop():
    """בדיקת התראות מחיר כל 5 דקות"""
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        d = get_data(symbol)
        if d and d['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel:
                        await channel.send(f"🚨 **התראת מחיר!** {symbol} חצתה את היעד: **${d['price']}**")
                        db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

@tasks.loop(time=time(hour=21, minute=30)) # 23:30 Israel Time
async def daily_report_task():
    """דוח סוף יום אוטומטי"""
    users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
    for (user_id,) in users:
        data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (user_id,))
        if not data: continue
        embed = discord.Embed(title="🌙 סיכום יום מסחר", color=0x2c3e50, timestamp=datetime.now())
        for sym, shares, avg_buy in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_buy) * shares
                embed.add_field(name=sym, value=f"מחיר: ${d['price']} ({d['change']:.2f}%)\nרווח יומי: ${pnl:,.2f}", inline=False)
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                if channel: await channel.send(embed=embed)

# --- 🛠️ Core Commands ---

@bot.command()
async def setup(ctx):
    """יוצר חדר פרטי מאובטח"""
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await ctx.guild.create_text_channel(f"💼-{ctx.author.display_name}", overwrites=overwrites)
    await ctx.send(f"✅ חדר פרטי נוצר: {channel.mention}")

@bot.command()
async def add(ctx, symbol: str, shares: float, price: float):
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol.upper(), shares, price))
    await ctx.send(f"✅ נוסף לתיק: {symbol.upper()} ב-${price}")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק ריק.")
    embed = discord.Embed(title="💼 תיק ההשקעות שלי", color=0x3498db)
    total_val = 0
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            val = shares * d['price']
            total_val += val
            embed.add_field(name=sym, value=f"כמות: {shares} | שווי: ${val:,.2f}", inline=False)
    embed.set_footer(text=f"שווי כולל: ${total_val:,.2f}")
    await ctx.send(embed=embed)

@bot.command()
async def stock(ctx, symbol: str):
    d = get_data(symbol)
    if d:
        chart_url = f"https://quickchart.io/chart?c={{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green'}}]}}}}"
        embed = discord.Embed(title=f"📊 {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=chart_url)
        await ctx.send(embed=embed)

@bot.command()
async def info(ctx, symbol: str):
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x2c3e50)
        embed.add_field(name="🏛️ בורסה", value=data.get('exchange', 'N/A'))
        embed.add_field(name="🏭 תחום", value=data.get('sector', 'N/A'))
        await ctx.send(embed=embed)
    except: await ctx.send("❌ לא נמצא מידע.")

@bot.command()
async def alert(ctx, symbol: str, price: float):
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 התראה הוגדרה ל-{symbol.upper()} ב-${price}")

@bot.command()
async def daily_on(ctx):
    db_execute("INSERT INTO user_settings (user_id, daily_updates) VALUES (%s, True) ON CONFLICT (user_id) DO UPDATE SET daily_updates = True", (ctx.author.id,))
    await ctx.send("🔔 עדכונים יומיים הופעלו!")

@bot.command()
async def daily_off(ctx):
    db_execute("UPDATE user_settings SET daily_updates = False WHERE user_id = %s", (ctx.author.id,))
    await ctx.send("🔕 עדכונים יומיים כובו.")

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    d = get_data(symbol)
    if d: await ctx.send(f"💰 {amount} {symbol.upper()} = **${amount * d['price']:,.2f}**")

@bot.command()
async def risk(ctx):
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("אין נתונים.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח סיכונים", color=0xe74c3c)
    for sym, val in data: embed.add_field(name=sym, value=f"{(val/total)*100:.1f}% מהתיק")
    await ctx.send(embed=embed)

@bot.command()
async def market(ctx):
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    embed = discord.Embed(title="🌍 מדדי שוק", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d: embed.add_field(name=name, value=f"${d['price']:,.2f} ({d['change']:.2f}%)")
    await ctx.send(embed=embed)

@bot.command()
async def help_me(ctx):
    await ctx.send("**🤖 פקודות:** `!setup`, `!add`, `!my_p`, `!stock`, `!info`, `!alert`, `!daily_on`, `!daily_off`, `!convert`, `!risk`, `!market`")

# --- Run ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
