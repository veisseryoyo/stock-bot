import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime

# --- הגדרת Flask עבור Koyeb (שומר על הבוט ער) ---
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

# --- פונקציות משיכת נתונים משופרות ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        
        # משיכת היסטוריה לגרף שבועי
        hist_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=7d&interval=1d"
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
intents.members = True # דורש הפעלה ב-Discord Developer Portal
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט המלא של יהונתן באוויר!')
    if not daily_report.is_running():
        daily_report.start()

# --- 1. מערכת חדרים פרטיים ---
@bot.command()
async def setup(ctx):
    """יוצר חדר פרטי מאובטח למשתמש"""
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
        return await ctx.send(f"❌ כבר יש לך חדר פרטי: {existing_channel.mention}")

    channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
    embed = discord.Embed(title="🚀 ברוך הבא לחדר הפיננסי שלך!", color=0x2ecc71)
    embed.description = f"כאן תוכל לנהל את ההשקעות שלך בפרטיות מוחלטת.\n\n**פקודות להתחלה:**\n`!add [Symbol] [Amount] [Price]`\n`!my_p`"
    await channel.send(member.mention, embed=embed)
    await ctx.send(f"✅ יצרתי לך חדר פרטי: {channel.mention}")

# --- 2. עדכונים יומיים אוטומטיים ---
@tasks.loop(hours=24)
async def daily_report():
    users = db_fetch("SELECT DISTINCT user_id FROM portfolios")
    for (user_id,) in users:
        data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (user_id,))
        if not data: continue
        
        embed = discord.Embed(title="📅 דוח רווחים יומי", color=0x3498db, timestamp=datetime.now())
        total_pnl = 0
        for sym, shares, avg_buy in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_buy) * shares
                total_pnl += pnl
                embed.add_field(name=sym, value=f"מחיר: ${d['price']} | שינוי יומי: {d['change']:.2f}%\nרווח/הפסד: ${pnl:,.2f}", inline=False)
        
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                if channel: await channel.send(embed=embed)

# --- 3. פקודות ניהול תיק ---
@bot.command()
async def add(ctx, symbol: str, shares: float, price: float):
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol, shares, price))
    await ctx.send(f"✅ שמרתי {shares} יחידות של {symbol} במחיר ${price} ב-Supabase!")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק שלך ריק. השתמש ב-`!add`.")
    
    embed = discord.Embed(title="💼 תיק ההשקעות שלי", color=0x1abc9c)
    total_val, total_profit = 0, 0
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            cur_val = shares * d['price']
            profit = cur_val - (shares * avg_buy)
            total_val += cur_val
            total_profit += profit
            emoji = "📈" if profit >= 0 else "📉"
            embed.add_field(name=f"{emoji} {sym}", value=f"כמות: {shares} | שווי: ${cur_val:,.2f}\nרווח: ${profit:,.2f}", inline=False)
    
    embed.set_footer(text=f"סה''כ שווי: ${total_val:,.2f} | רווח כולל: ${total_profit:,.2f}")
    await ctx.send(embed=embed)

# --- 4. פקודות מידע וניתוח שוק ---
@bot.command()
async def stock(ctx, symbol: str):
    d = get_data(symbol)
    if d:
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green',fill:false}}]}}}}"
        url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_config)}"
        embed = discord.Embed(title=f"📊 מניית {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

@bot.command()
async def news(ctx, symbol: str):
    articles = get_news(symbol)
    if not articles: return await ctx.send("❌ לא נמצאו חדשות.")
    embed = discord.Embed(title=f"📰 חדשות עבור {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לכתבה המלאה]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def risk(ctx):
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("אין נתונים לניתוח.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח פיזור סיכונים", color=0xe74c3c)
    for sym, val in data:
        perc = (val / total) * 100
        embed.add_field(name=sym, value=f"חשיפה: {perc:.1f}% מהתיק", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def calc(ctx, budget: float, symbol: str):
    d = get_data(symbol)
    if d:
        count = budget / d['price']
        await ctx.send(f"🛍️ עם ${budget:,.2f} תוכל לקנות **{count:.2f}** יחידות של {symbol.upper()}.")

@bot.command()
async def market(ctx):
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    embed = discord.Embed(title="🌍 מדדי שוק מרכזיים", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d:
            emoji = "🟢" if d['change'] >= 0 else "🔴"
            embed.add_field(name=name, value=f"{emoji} ${d['price']:,.2f} ({d['change']:.2f}%)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def stats(ctx, symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        meta = res['chart']['result'][0]['meta']
        embed = discord.Embed(title=f"📈 נתונים שנתיים: {symbol.upper()}", color=0x1abc9c)
        embed.add_field(name="גבוה שנתי", value=f"${meta.get('fiftyTwoWeekHigh', 'N/A')}")
        embed.add_field(name="נמוך שנתי", value=f"${meta.get('fiftyTwoWeekLow', 'N/A')}")
        await ctx.send(embed=embed)
    except: await ctx.send("תקלה במשיכת סטטיסטיקות.")

@bot.command()
async def help_me(ctx):
    msg = """
**🤖 פקודות בוט Founder Finance:**
`!setup` - יצירת חדר פרטי
`!add [SYM] [QTY] [PRICE]` - הוספה לתיק
`!my_p` - הצגת התיק ורווחים
`!stock [SYM]` - מחיר + גרף
`!news [SYM]` - חדשות חמות
`!market` - מצב השוק העולמי
`!risk` - ניתוח פיזור תיק
`!calc [$$] [SYM]` - חישוב כמות קנייה
`!stats [SYM]` - נתוני שנה אחרונה
    """
    await ctx.send(msg)

# --- הרצה ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
