import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime

# --- Flask Server (Keep Alive) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Stock Bot is Active"
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

# --- Data Fetching Functions ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA"]: sym += "-USD"
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
            "history": history
        }
    except: return None

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט המלא של יהונתן באוויר!')
    if not background_tasks.is_running():
        background_tasks.start()

# --- Background Tasks (Daily Report & Price Alerts) ---
@tasks.loop(minutes=5)
async def background_tasks():
    # בדיקת התראות מחיר
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        data = get_data(symbol)
        if data and data['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel:
                        await channel.send(f"🚨 **התראת מחיר!** {symbol} הגיעה ליעד שלך: **${data['price']}**")
                        db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

# --- Commands ---

@bot.command()
async def setup(ctx):
    """יצירת חדר פרטי"""
    guild = ctx.guild
    member = ctx.author
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel_name = f"💼-{member.display_name}"
    channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
    await ctx.send(f"✅ חדר פרטי נוצר: {channel.mention}")

@bot.command()
async def add(ctx, symbol: str, shares: float, price: float):
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol.upper(), shares, price))
    await ctx.send(f"✅ נוסף לתיק: {symbol.upper()} ({shares} יחידות)")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק ריק.")
    embed = discord.Embed(title="💼 תיק השקעות", color=0x3498db)
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            cur_val = shares * d['price']
            profit = cur_val - (shares * avg_buy)
            emoji = "📈" if profit >= 0 else "📉"
            embed.add_field(name=f"{emoji} {sym}", value=f"שווי: ${cur_val:,.2f}\nרווח: ${profit:,.2f}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def stock(ctx, symbol: str):
    d = get_data(symbol)
    if d:
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green'}}]}}}}"
        url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_config)}"
        embed = discord.Embed(title=f"📊 {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

@bot.command()
async def info(ctx, symbol: str):
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x2c3e50)
        embed.add_field(name="🏛️ בורסה", value=data.get('exchange', 'N/A'), inline=True)
        embed.add_field(name="🏭 תחום", value=data.get('sector', 'N/A'), inline=True)
        await ctx.send(embed=embed)
    except: await ctx.send("❌ לא נמצא מידע.")

@bot.command()
async def alert(ctx, symbol: str, price: float):
    """הגדרת התראת מחיר: !alert AAPL 250"""
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 הוגדרה התראה ל-{symbol.upper()} במחיר של ${price}")

@bot.command()
async def market(ctx):
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    embed = discord.Embed(title="🌍 מצב השוק", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d:
            emoji = "🟢" if d['change'] >= 0 else "🔴"
            embed.add_field(name=name, value=f"{emoji} ${d['price']:,.2f} ({d['change']:.2f}%)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def help_me(ctx):
    commands_list = "`!setup`, `!add`, `!my_p`, `!stock`, `!info`, `!alert`, `!market`"
    await ctx.send(f"🤖 **פקודות זמינות:**\n{commands_list}")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
