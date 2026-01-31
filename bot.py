import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, time

# --- Flask Server (שומר על הבוט פעיל 24/7) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Stock Bot is FULLY Operational - Multi-Portfolio Mode"
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

# --- מנוע משיכת נתונים (מניות + קריפטו + היסטוריה) ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        
        # משיכת היסטוריה לגרף (7 ימים אחרונים)
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

# --- הגדרות הבוט ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, הבוט המלא ללא קיצורים באוויר!')
    if not background_tasks_loop.is_running(): background_tasks_loop.start()
    if not daily_report_loop.is_running(): daily_report_loop.start()

# --- 🔄 משימות רקע (התראות ודוחות) ---

@tasks.loop(minutes=5)
async def background_tasks_loop():
    """בדיקת התראות מחיר חכמה"""
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        d = get_data(symbol)
        if d and d['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel:
                        await channel.send(f"🚨 **התראת מחיר ליהונתן!** {symbol} הגיעה ליעד: **${d['price']}**")
                        db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

@tasks.loop(time=time(hour=21, minute=30)) # 23:30 שעון ישראל
async def daily_report_loop():
    """דוח סוף יום לכל התיקים"""
    users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
    for (user_id,) in users:
        data = db_fetch("SELECT portfolio_name, symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY portfolio_name, symbol", (user_id,))
        if not data: continue
        embed = discord.Embed(title="🌙 דוח סוף יום - כל התיקים שלך", color=0x2c3e50, timestamp=datetime.now())
        for p_name, sym, shares, avg_buy in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_buy) * shares
                embed.add_field(name=f"[{p_name}] {sym}", value=f"מחיר: ${d['price']} | שינוי: {d['change']:.2f}%\nרווח/הפסד: ${pnl:,.2f}", inline=False)
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                if channel: await channel.send(embed=embed)

# --- 📂 פקודות ניהול תיקים מרובים ---

@bot.command()
async def create_p(ctx, name: str):
    """הגדרת שם תיק חדש"""
    await ctx.send(f"✅ תיק בשם **{name}** הוגדר במערכת. עכשיו תוכל להוסיף אליו מניות.")

@bot.command()
async def list_p(ctx):
    """רשימת כל התיקים הקיימים"""
    data = db_fetch("SELECT DISTINCT portfolio_name FROM portfolios WHERE user_id = %s", (ctx.author.id,))
    if not data: return await ctx.send("📪 אין לך תיקים עדיין. השתמש ב-`!create_p`.")
    names = "\n".join([f"• {row[0]}" for row in data])
    await ctx.send(f"📂 **התיקים שלך:**\n{names}")

@bot.command()
async def add(ctx, portfolio_name: str, symbol: str, shares: float, price: float = 0):
    """הוספה לתיק ספציפי (אם מחיר=0, יילקח מחיר שוק)"""
    symbol = symbol.upper()
    if price == 0:
        await ctx.send(f"🔍 מושך מחיר שוק עבור {symbol}...")
        d = get_data(symbol)
        if d: price = d['price']
        else: return await ctx.send("❌ לא מצאתי מחיר שוק, אנא הזן ידנית.")
    
    db_execute("INSERT INTO portfolios (user_id, portfolio_name, symbol, shares, buy_price) VALUES (%s, %s, %s, %s, %s)", 
               (ctx.author.id, portfolio_name, symbol, shares, price))
    await ctx.send(f"✅ הוספתי {shares} יחידות של {symbol} לתיק **{portfolio_name}** במחיר ${price:,.2f}.")

@bot.command()
async def my_p(ctx, portfolio_name: str = None):
    """הצגת תיק ספציפי או סיכום הכל"""
    query = "SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s"
    params = [ctx.author.id]
    if portfolio_name:
        query += " AND portfolio_name = %s GROUP BY symbol"
        params.append(portfolio_name)
        title = f"💼 תיק: {portfolio_name}"
    else:
        query += " GROUP BY symbol"
        title = "💼 כלל הנכסים שלי"

    data = db_fetch(query, tuple(params))
    if not data: return await ctx.send("📪 אין נתונים להצגה.")
    
    embed = discord.Embed(title=title, color=0x3498db)
    total_val = 0
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            val = shares * d['price']
            total_val += val
            embed.add_field(name=sym, value=f"כמות: {shares} | שווי: ${val:,.2f}", inline=False)
    embed.set_footer(text=f"שווי כולל: ${total_val:,.2f}")
    await ctx.send(embed=embed)

# --- 📊 פקודות מידע וניתוח (ללא קיצורים) ---

@bot.command()
async def stock(ctx, symbol: str):
    """מחיר וגרף 7 ימים"""
    d = get_data(symbol)
    if d:
        chart_url = f"https://quickchart.io/chart?c={{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green',fill:false}}]}}}}"
        embed = discord.Embed(title=f"📊 מניית {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר נוכחי", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי יומי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=chart_url)
        await ctx.send(embed=embed)

@bot.command()
async def info(ctx, symbol: str):
    """מידע חברה מורחב"""
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x2c3e50)
        embed.add_field(name="🏛️ בורסה", value=data.get('exchange', 'N/A'), inline=True)
        embed.add_field(name="🏭 תחום", value=data.get('sector', 'N/A'), inline=True)
        embed.add_field(name="🌍 מדינה", value=data.get('country', 'N/A'), inline=True)
        await ctx.send(embed=embed)
    except: await ctx.send("❌ מידע לא זמין.")

@bot.command()
async def news(ctx, symbol: str):
    """חדשות אחרונות"""
    articles = get_news(symbol)
    if not articles: return await ctx.send("אין חדשות כרגע.")
    embed = discord.Embed(title=f"📰 חדשות: {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לינק לכתבה]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    """הגדרת התראת מחיר"""
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 התראה הוגדרה ל-{symbol.upper()} ב-${price}")

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    """המרה מהירה לשווי דולרי"""
    d = get_data(symbol)
    if d:
        total = amount * d['price']
        await ctx.send(f"💰 **{amount}** יחידות של {symbol.upper()} = **${total:,.2f}**")

@bot.command()
async def risk(ctx):
    """ניתוח חשיפה בתיק"""
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 אין נתונים לחישוב.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח סיכונים וחשיפה", color=0xe74c3c)
    for sym, val in data:
        embed.add_field(name=sym, value=f"{(val/total)*100:.1f}% מההשקעה", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def market(ctx):
    """מדדי עולם בזמן אמת"""
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"}
    embed = discord.Embed(title="🌍 מצב השוק העולמי", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d:
            emoji = "🟢" if d['change'] >= 0 else "🔴"
            embed.add_field(name=name, value=f"{emoji} ${d['price']:,.2f} ({d['change']:.2f}%)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def stats(ctx, symbol: str):
    """נתונים טכניים שנתיים"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        meta = res['chart']['result'][0]['meta']
        embed = discord.Embed(title=f"📈 נתונים שנתיים: {symbol.upper()}", color=0x1abc9c)
        embed.add_field(name="גבוה שנתי", value=f"${meta.get('fiftyTwoWeekHigh', 'N/A')}")
        embed.add_field(name="נמוך שנתי", value=f"${meta.get('fiftyTwoWeekLow', 'N/A')}")
        await ctx.send(embed=embed)
    except: await ctx.send("❌ שגיאה במשיכת נתונים.")

@bot.command()
async def setup(ctx):
    """יצירת חדר פרטי"""
    overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True), ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    channel = await ctx.guild.create_text_channel(f"💼-{ctx.author.display_name}", overwrites=overwrites)
    await ctx.send(f"✅ חדר פרטי נוצר עבורך: {channel.mention}")

@bot.command()
async def daily_on(ctx):
    """הפעלת דוח סוף יום"""
    db_execute("INSERT INTO user_settings (user_id, daily_updates) VALUES (%s, True) ON CONFLICT (user_id) DO UPDATE SET daily_updates = True", (ctx.author.id,))
    await ctx.send("🔔 דוחות לילה הופעלו!")

@bot.command()
async def help_me(ctx):
    """מדריך פקודות מלא"""
    msg = """**🤖 פקודות בוט yoyo Stock:**
`!create_p [NAME]` - יצירת תיק חדש
`!list_p` - רשימת התיקים שלי
`!add [PORTFOLIO] [SYM] [QTY] (PRICE)` - הוספה לתיק
`!my_p (PORTFOLIO)` - הצגת התיק שלך
`!stock [SYM]` - גרף ומחיר
`!info [SYM]` - מידע חברה
`!news [SYM]` - חדשות חמות
`!alert [SYM] [PRICE]` - התראת מחיר
`!convert [QTY] [SYM]` - שווי דולרי
`!risk` - ניתוח חשיפה
`!market` - מצב המדדים בעולם
`!stats [SYM]` - גבוה/נמוך שנתי
`!setup` - חדר פרטי
`!daily_on` - הפעלת דוחות לילה"""
    await ctx.send(msg)

# --- הרצת הבוט ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
