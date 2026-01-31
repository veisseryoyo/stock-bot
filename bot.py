import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime

# --- הגדרת Flask עבור Koyeb (Health Check & Keep Alive) ---
app = Flask('')
@app.route('/')
def home(): return "Pro Financial Bot is Online & Awake"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- חיבור למסד הנתונים Supabase ---
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

# --- פונקציות משיכת נתונים ---
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
            "history": history
        }
    except: return None

def get_news(symbol):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get('news', [])[:3]
    except: return []

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט המלא של יהונתן באוויר וללא שגיאות!')
    if not daily_report.is_running():
        daily_report.start()

# --- פקודות חשבון וחדרים ---
@bot.command()
async def setup(ctx):
    """יוצר חדר פרטי למשתמש"""
    guild = ctx.guild
    member = ctx.author
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel_name = f"💼-{member.display_name}"
    
    existing_channel = discord.utils.get(guild.channels, name=channel_name.lower())
    if existing_channel:
        return await ctx.send(f"❌ יהונתן, כבר יש לך חדר פרטי: {existing_channel.mention}")

    channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
    embed = discord.Embed(title="🚀 ברוך הבא לחדר הפרטי!", color=0x2ecc71)
    embed.description = "כל הפעולות בחדר זה מוסתרות משאר השרת.\nתתחיל ב-`!add` כדי לבנות את התיק שלך."
    await channel.send(member.mention, embed=embed)
    await ctx.send(f"✅ החדר נוצר: {channel.mention}")

# --- פקודות ניהול תיק (Supabase) ---
@bot.command()
async def add(ctx, symbol: str, shares: float, price: float):
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol, shares, price))
    await ctx.send(f"✅ הוספתי {shares} יחידות של {symbol} במחיר ${price} לתיק שלך.")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק ריק.")
    
    embed = discord.Embed(title="💼 תיק השקעות", color=0x3498db)
    total_val, total_profit = 0, 0
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            cur_val = shares * d['price']
            profit = cur_val - (shares * avg_buy)
            total_val += cur_val
            total_profit += profit
            emoji = "📈" if profit >= 0 else "📉"
            embed.add_field(name=f"{emoji} {sym}", value=f"שווי: ${cur_val:,.2f} | רווח: ${profit:,.2f}", inline=False)
    
    embed.set_footer(text=f"שווי כולל: ${total_val:,.2f} | רווח/הפסד מצטבר: ${total_profit:,.2f}")
    await ctx.send(embed=embed)

# --- פקודות מידע וניתוח ---
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
    """מידע על החברה"""
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x34495e)
        embed.add_field(name="תחום", value=data.get('sector', 'N/A'))
        embed.add_field(name="בורסה", value=data.get('exchange', 'N/A'))
        await ctx.send(embed=embed)
    except: await ctx.send("❌ לא נמצא מידע.")

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    """המרת כמות מניות לשווי דולרי"""
    d = get_data(symbol)
    if d:
        res = amount * d['price']
        await ctx.send(f"💰 {amount} מניות של {symbol.upper()} שוות **${res:,.2f}**")

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
async def news(ctx, symbol: str):
    articles = get_news(symbol)
    if not articles: return await ctx.send("אין חדשות כרגע.")
    embed = discord.Embed(title=f"📰 חדשות עבור {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לינק]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def risk(ctx):
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("אין נתונים.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ פיזור סיכונים", color=0xe74c3c)
    for sym, val in data:
        embed.add_field(name=sym, value=f"{(val/total)*100:.1f}% מהתיק", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def stats(ctx, symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        meta = res['chart']['result'][0]['meta']
        embed = discord.Embed(title=f"📈 נתונים שנתיים: {symbol.upper()}", color=0x1abc9c)
        embed.add_field(name="גבוה שנתי", value=f"${meta.get('fiftyTwoWeekHigh')}")
        embed.add_field(name="נמוך שנתי", value=f"${meta.get('fiftyTwoWeekLow')}")
        await ctx.send(embed=embed)
    except: await ctx.send("שגיאה במשיכת נתונים.")

@bot.command()
async def help_me(ctx):
    msg = "**🤖 פקודות בוט:**\n`!setup`, `!add`, `!my_p`, `!stock`, `!info`, `!news`, `!market`, `!risk`, `!convert`, `!stats`"
    await ctx.send(msg)

# --- לולאות אוטומטיות ---
@tasks.loop(hours=24)
async def daily_report():
    users = db_fetch("SELECT DISTINCT user_id FROM portfolios")
    for (user_id,) in users:
        # כאן תבוא הלוגיקה לשליחת דוח לכל משתמש בחדר שלו
        pass

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
