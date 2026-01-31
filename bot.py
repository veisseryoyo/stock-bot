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
def home(): return "Yoyo Stock Bot is Active & Awake"
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
    if not background_tasks.is_running():
        background_tasks.start()

# --- לולאת משימות רקע (התראות מחיר ודוחות) ---
@tasks.loop(minutes=5)
async def background_tasks():
    # בדיקת התראות מחיר פעילות
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        data = get_data(symbol)
        if data and data['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel:
                        await channel.send(f"🚨 **התראת מחיר!** המניה {symbol} הגיעה ליעד שלך: **${data['price']}**")
                        db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

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
    embed = discord.Embed(title="🚀 ברוך הבא לחדר הפיננסי שלך!", color=0x2ecc71)
    embed.description = "כאן תוכל לנהל את ההשקעות שלך בפרטיות מוחלטת.\nכל הפעולות שתבצע בחדר זה מוסתרות משאר השרת."
    await channel.send(member.mention, embed=embed)
    await ctx.send(f"✅ החדר נוצר בהצלחה: {channel.mention}")

# --- פקודות ניהול תיק השקעות ---
@bot.command()
async def add(ctx, symbol: str, shares: float, price: float):
    """הוספת מניה לתיק: !add [SYM] [QTY] [BUY_PRICE]"""
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol, shares, price))
    await ctx.send(f"✅ הוספתי לתיק שלך {shares} יחידות של {symbol} במחיר קנייה של ${price}.")

@bot.command()
async def my_p(ctx):
    """הצגת תיק השקעות ורווח/הפסד"""
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק שלך ריק כרגע.")
    
    embed = discord.Embed(title="💼 תיק ההשקעות של יהונתן", color=0x3498db)
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
    
    embed.set_footer(text=f"שווי כולל: ${total_val:,.2f} | רווח/הפסד כולל: ${total_profit:,.2f}")
    await ctx.send(embed=embed)

# --- פקודות מידע וניתוח שוק ---
@bot.command()
async def stock(ctx, symbol: str):
    """מחיר נוכחי וגרף שבועי"""
    d = get_data(symbol)
    if d:
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green',fill:false}}]}}}}"
        url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_config)}"
        embed = discord.Embed(title=f"📊 מניית {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר נוכחי", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי יומי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

@bot.command()
async def info(ctx, symbol: str):
    """מידע מפורט על החברה"""
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x2c3e50)
        embed.add_field(name="🏛️ בורסה", value=data.get('exchange', 'N/A'), inline=True)
        embed.add_field(name="🏭 תחום", value=data.get('sector', 'N/A'), inline=True)
        embed.add_field(name="🌍 מדינה", value=data.get('country', 'N/A'), inline=True)
        await ctx.send(embed=embed)
    except: await ctx.send(f"❌ לא נמצא מידע על {symbol.upper()}")

@bot.command()
async def news(ctx, symbol: str):
    """חדשות אחרונות על מניה"""
    articles = get_news(symbol)
    if not articles: return await ctx.send("❌ אין חדשות כרגע.")
    embed = discord.Embed(title=f"📰 חדשות עבור {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לכתבה המלאה]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    """הגדרת התראת מחיר"""
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 הוגדרה התראה! אני אעדכן אותך כש-{symbol.upper()} תגיע ל-${price}")

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    """המרת כמות מניות לשווי דולרי"""
    d = get_data(symbol)
    if d:
        res = amount * d['price']
        await ctx.send(f"💰 **{amount}** יחידות של {symbol.upper()} שוות כרגע **${res:,.2f}**")

@bot.command()
async def market(ctx):
    """מצב המדדים בעולם"""
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    embed = discord.Embed(title="🌍 תמונת מצב שוק עולמי", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d:
            emoji = "🟢" if d['change'] >= 0 else "🔴"
            embed.add_field(name=name, value=f"{emoji} ${d['price']:,.2f} ({d['change']:.2f}%)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def risk(ctx):
    """ניתוח סיכוני תיק השקעות"""
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק ריק, אין מה לנתח.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח פיזור סיכונים", color=0xe74c3c)
    for sym, val in data:
        perc = (val / total) * 100
        embed.add_field(name=sym, value=f"חשיפה: {perc:.1f}% מהתיק", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def stats(ctx, symbol: str):
    """סטטיסטיקות שנתיות"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        meta = res['chart']['result'][0]['meta']
        embed = discord.Embed(title=f"📈 נתונים שנתיים: {symbol.upper()}", color=0x1abc9c)
        embed.add_field(name="גבוה 52 שבועות", value=f"${meta.get('fiftyTwoWeekHigh', 'N/A')}")
        embed.add_field(name="נמוך 52 שבועות", value=f"${meta.get('fiftyTwoWeekLow', 'N/A')}")
        await ctx.send(embed=embed)
    except: await ctx.send("❌ שגיאה במשיכת סטטיסטיקות.")

@bot.command()
async def help_me(ctx):
    """רשימת כל פקודות הבוט"""
    msg = """
**🤖 פקודות בוט yoyo Stock:**
`!setup` - יצירת חדר פרטי מאובטח
`!add [SYM] [QTY] [PRICE]` - הוספת מניה לתיק
`!my_p` - הצגת התיק וחישוב רווחיות
`!stock [SYM]` - מחיר נוכחי וגרף שבועי
`!info [SYM]` - מידע מפורט על החברה
`!alert [SYM] [PRICE]` - הגדרת התראת מחיר
`!news [SYM]` - חדשות חמות
`!market` - מצב המדדים המובילים
`!risk` - ניתוח פיזור סיכוני תיק
`!convert [QTY] [SYM]` - חישוב שווי דולרי
`!stats [SYM]` - נתוני גבוה/נמוך שנתי
    """
    await ctx.send(msg)

# --- הרצה ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
