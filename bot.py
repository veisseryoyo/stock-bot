import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime, time

# --- Flask Server (שומר על הבוט ער ב-Koyeb) ---
app = Flask('')
@app.route('/')
def home(): return "Yoyo Stock Bot is FULLY Operational"
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

# --- מנוע משיכת נתונים משופר ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL", "ADA", "DOGE"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        
        # היסטוריה לגרף (7 ימים)
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
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ יהונתן, הבוט המלא באוויר ללא קיצורים!')
    if not background_tasks.is_running():
        background_tasks.start()
    if not daily_report_task.is_running():
        daily_report_task.start()

# --- 🔄 מערכות אוטומטיות (התראות ודוחות) ---

@tasks.loop(minutes=5)
async def background_tasks():
    """בדיקת התראות מחיר"""
    alerts = db_fetch("SELECT id, user_id, symbol, target_price FROM alerts WHERE active = True")
    for alert_id, user_id, symbol, target in alerts:
        d = get_data(symbol)
        if d and d['price'] >= target:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                    if channel:
                        await channel.send(f"🚨 **התראת מחיר עבור יהונתן!** {symbol} חצתה את היעד שלך: **${d['price']}**")
                        db_execute("UPDATE alerts SET active = False WHERE id = %s", (alert_id,))

@tasks.loop(time=time(hour=21, minute=30)) # 23:30 שעון ישראל
async def daily_report_task():
    """שליחת דוח סוף יום למי שהפעיל !daily_on"""
    users = db_fetch("SELECT user_id FROM user_settings WHERE daily_updates = True")
    for (user_id,) in users:
        data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (user_id,))
        if not data: continue
        
        embed = discord.Embed(title="🌙 סיכום יום המסחר שלך", color=0x2c3e50, timestamp=datetime.now())
        total_pnl = 0
        for sym, shares, avg_buy in data:
            d = get_data(sym)
            if d:
                pnl = (d['price'] - avg_buy) * shares
                total_pnl += pnl
                status = "📈" if d['change'] >= 0 else "📉"
                embed.add_field(name=f"{status} {sym}", value=f"מחיר: ${d['price']} ({d['change']:.2f}%)\nרווח/הפסד: ${pnl:,.2f}", inline=False)
        
        embed.description = f"**סה''כ רווח/הפסד יומי: ${total_pnl:,.2f}**"
        
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                channel = discord.utils.get(guild.channels, name=f"💼-{member.display_name}".lower())
                if channel: await channel.send(embed=embed)

# --- 🛠️ פקודות הבוט ---

@bot.command()
async def setup(ctx):
    """יוצר חדר פרטי למשתמש"""
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel_name = f"💼-{ctx.author.display_name}"
    existing = discord.utils.get(ctx.guild.channels, name=channel_name.lower())
    if existing: return await ctx.send(f"❌ כבר יש לך חדר: {existing.mention}")
    
    channel = await ctx.guild.create_text_channel(channel_name, overwrites=overwrites)
    embed = discord.Embed(title="🚀 חדר פיננסי אישי", color=0x2ecc71, description="כאן מנהלים את הכסף בפרטיות!")
    await channel.send(ctx.author.mention, embed=embed)
    await ctx.send(f"✅ יצרתי לך חדר: {channel.mention}")

@bot.command()
async def add(ctx, symbol: str, shares: float, price: float = 0):
    """הוספת מניה - אם לא תשים מחיר, יילקח מחיר השוק"""
    symbol = symbol.upper()
    if price == 0:
        await ctx.send(f"🔍 מושך מחיר עדכני עבור {symbol}...")
        d = get_data(symbol)
        if d: price = d['price']
        else: return await ctx.send("❌ לא מצאתי מחיר שוק, אנא הזן ידנית.")
    
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol, shares, price))
    await ctx.send(f"✅ נוסף לתיק: **{shares}** יחידות של **{symbol}** ב מחיר **${price:,.2f}**")

@bot.command()
async def my_p(ctx):
    """הצגת התיק ורווחים"""
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("📪 התיק ריק.")
    
    embed = discord.Embed(title="💼 תיק ההשקעות שלי", color=0x3498db)
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
    
    embed.set_footer(text=f"שווי כולל: ${total_val:,.2f} | רווח מצטבר: ${total_profit:,.2f}")
    await ctx.send(embed=embed)

@bot.command()
async def stock(ctx, symbol: str):
    """מחיר וגרף"""
    d = get_data(symbol)
    if d:
        chart_url = f"https://quickchart.io/chart?c={{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol.upper()}',data:{d['history']},borderColor:'green'}}]}}}}"
        embed = discord.Embed(title=f"📊 מניית {symbol.upper()}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${d['price']}", inline=True)
        embed.add_field(name="שינוי", value=f"{d['change']:.2f}%", inline=True)
        embed.set_image(url=chart_url)
        await ctx.send(embed=embed)

@bot.command()
async def info(ctx, symbol: str):
    """מידע מפורט על החברה"""
    url = f"https://query2.finance.yahoo.com/v1/finance/quoteType/?symbol={symbol.upper()}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        data = res['quoteType']['result'][0]
        embed = discord.Embed(title=f"🏢 {data.get('longName', symbol.upper())}", color=0x2c3e50)
        embed.add_field(name="🏛️ בורסה", value=data.get('exchange', 'N/A'), inline=True)
        embed.add_field(name="🏭 תחום", value=data.get('sector', 'N/A'), inline=True)
        embed.add_field(name="🌍 מדינה", value=data.get('country', 'N/A'), inline=True)
        await ctx.send(embed=embed)
    except: await ctx.send("❌ מידע לא נמצא.")

@bot.command()
async def news(ctx, symbol: str):
    """חדשות חמות"""
    articles = get_news(symbol)
    if not articles: return await ctx.send("אין חדשות כרגע.")
    embed = discord.Embed(title=f"📰 חדשות עבור {symbol.upper()}", color=0xf1c40f)
    for art in articles:
        embed.add_field(name=art['title'], value=f"[לינק]({art['link']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def alert(ctx, symbol: str, price: float):
    """הצבת התראת מחיר"""
    db_execute("INSERT INTO alerts (user_id, symbol, target_price, active) VALUES (%s, %s, %s, %s)", (ctx.author.id, symbol.upper(), price, True))
    await ctx.send(f"🎯 יעד נקבע! אעדכן אותך כש-{symbol.upper()} תגיע ל-${price}")

@bot.command()
async def daily_on(ctx):
    """הפעלת דוחות לילה"""
    db_execute("INSERT INTO user_settings (user_id, daily_updates) VALUES (%s, True) ON CONFLICT (user_id) DO UPDATE SET daily_updates = True", (ctx.author.id,))
    await ctx.send("🔔 יהונתן, דוחות סוף יום הופעלו!")

@bot.command()
async def daily_off(ctx):
    """כיבוי דוחות לילה"""
    db_execute("UPDATE user_settings SET daily_updates = False WHERE user_id = %s", (ctx.author.id,))
    await ctx.send("🔕 דוחות כובו.")

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    """המרה מהירה של מניות לדולר"""
    d = get_data(symbol)
    if d: await ctx.send(f"💰 {amount} {symbol.upper()} = **${amount * d['price']:,.2f}**")

@bot.command()
async def risk(ctx):
    """ניתוח חשיפה בתיק"""
    data = db_fetch("SELECT symbol, SUM(shares * buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("אין נתונים לסיכונים.")
    total = sum(row[1] for row in data)
    embed = discord.Embed(title="⚠️ ניתוח סיכונים", color=0xe74c3c)
    for sym, val in data: embed.add_field(name=sym, value=f"{(val/total)*100:.1f}% מהתיק")
    await ctx.send(embed=embed)

@bot.command()
async def market(ctx):
    """מצב המדדים"""
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    embed = discord.Embed(title="🌍 מדדי שוק מרכזיים", color=0x9b59b6)
    for name, sym in indices.items():
        d = get_data(sym)
        if d: embed.add_field(name=name, value=f"${d['price']:,.2f} ({d['change']:.2f}%)")
    await ctx.send(embed=embed)

@bot.command()
async def stats(ctx, symbol: str):
    """נתונים שנתיים"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        meta = res['chart']['result'][0]['meta']
        embed = discord.Embed(title=f"📈 נתונים שנתיים: {symbol.upper()}", color=0x1abc9c)
        embed.add_field(name="גבוה שנתי", value=f"${meta.get('fiftyTwoWeekHigh')}")
        embed.add_field(name="נמוך שנתי", value=f"${meta.get('fiftyTwoWeekLow')}")
        await ctx.send(embed=embed)
    except: await ctx.send("שגיאה בסטטיסטיקות.")

@bot.command()
async def help_me(ctx):
    """תפריט עזרה מלא"""
    msg = """**🤖 כל הפקודות של yoyo Stock:**
`!setup` - חדר פרטי
`!add [SYM] [QTY] (PRICE)` - הוספה (מחיר אופציונלי)
`!my_p` - תיק השקעות ורווחים
`!stock [SYM]` - גרף ומחיר
`!info [SYM]` - מידע חברה
`!news [SYM]` - חדשות
`!alert [SYM] [PRICE]` - התראת מחיר
`!daily_on/off` - דוחות לילה
`!convert [QTY] [SYM]` - המרת שווי
`!risk` - ניתוח תיק
`!market` - מצב השוק
`!stats [SYM]` - גבוה/נמוך שנתי"""
    await ctx.send(msg)

# --- הפעלה ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
