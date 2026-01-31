import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread
from datetime import datetime

# --- Flask ל-Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"
def run_flask(): app.run(host='0.0.0.0', port=8000)

DATABASE_URL = "postgresql://postgres:Yoyov130113!@db.ouuieanhljwxiqlljwtv.supabase.co:5432/postgres"

# --- פונקציות מסד נתונים ---
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

# --- פונקציות נתונים ---
def get_data(symbol):
    sym = symbol.upper()
    if sym in ["BTC", "ETH", "SOL"]: sym += "-USD"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        return {"price": round(meta['regularMarketPrice'], 2), "change": ((meta['regularMarketPrice'] - meta['chartPreviousClose']) / meta['chartPreviousClose']) * 100}
    except: return None

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט של יהונתן מוכן!')
    if not daily_report.is_running():
        daily_report.start()

# --- 1. יצירת חדר פרטי לכל משתמש ---
@bot.command()
async def setup(ctx):
    """יוצר חדר פרטי למשתמש שרק הוא והבוט רואים"""
    guild = ctx.guild
    member = ctx.author
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel_name = f"💼-{member.display_name}"
    
    # בדיקה אם קיים כבר חדר
    existing_channel = discord.utils.get(guild.channels, name=channel_name.lower())
    if existing_channel:
        return await ctx.send(f"❌ יהונתן, כבר יש לך חדר פרטי: {existing_channel.mention}")

    channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
    await ctx.send(f"✅ יצרתי לך חדר פרטי בטוח! כנס ל-{channel.mention}")
    await channel.send(f"שלום {member.mention}! כאן תוכל לנהל את תיק ההשקעות שלך בצורה פרטית.")

# --- 2. עדכונים יומיים אוטומטיים ---
@tasks.loop(hours=24)
async def daily_report():
    """שולח דוח יומי לכל המשתמשים שיש להם מניות"""
    # שליפת כל המשתמשים הייחודיים במסד
    users = db_fetch("SELECT DISTINCT user_id FROM portfolios")
    for (user_id,) in users:
        data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (user_id,))
        if not data: continue
        
        embed = discord.Embed(title="📅 דוח שוק יומי", color=0x2ecc71, timestamp=datetime.now())
        total_profit = 0
        for sym, shares, avg_buy in data:
            d = get_data(sym)
            if d:
                profit = (d['price'] - avg_buy) * shares
                total_profit += profit
                embed.add_field(name=sym, value=f"מחיר: ${d['price']} | שינוי: {d['change']:.2f}%\nרווח: ${profit:,.2f}", inline=False)
        
        # ניסיון לשלוח לחדר הפרטי של המשתמש
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                channel_name = f"💼-{member.display_name}".lower()
                channel = discord.utils.get(guild.channels, name=channel_name)
                if channel:
                    await channel.send(embed=embed)
                    break

# --- פקודות ניהול (אותו דבר כמו קודם) ---
@bot.command()
async def add(ctx, symbol: str, shares: int, price: float):
    db_execute("INSERT INTO portfolios (user_id, symbol, shares, buy_price) VALUES (%s, %s, %s, %s)", 
               (ctx.author.id, symbol.upper(), shares, price))
    await ctx.send(f"✅ נוסף לתיק: {symbol.upper()}")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares), AVG(buy_price) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data: return await ctx.send("התיק ריק.")
    embed = discord.Embed(title="💼 התיק שלך", color=0x3498db)
    for sym, shares, avg_buy in data:
        d = get_data(sym)
        if d:
            val = shares * d['price']
            embed.add_field(name=sym, value=f"שווי: ${val:,.2f}", inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
