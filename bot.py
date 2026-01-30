import discord
from discord.ext import commands, tasks
import requests
import os
import sqlite3

# הגדרות בוט
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# פונקציות עזר למסד נתונים
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # טבלת תיקי השקעות
    c.execute('''CREATE TABLE IF NOT EXISTS portfolios 
                 (user_id INTEGER, symbol TEXT, shares INTEGER)''')
    # טבלת התראות
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (user_id INTEGER, symbol TEXT, target_price REAL)''')
    conn.commit()
    conn.close()

def update_db(query, params):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def fetch_db(query, params=()):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall()
    conn.close()
    return res

# פונקציית מחיר (Finnhub)
def get_stock_data(symbol):
    api_key = os.environ.get('FINNHUB_KEY')
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol.upper()}&token={api_key}"
    try:
        res = requests.get(url).json()
        return res.get('c'), res.get('dp')
    except:
        return None, None

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user.name} מחובר והמסד נתונים מוכן!")
    check_alerts.start()

@bot.command()
async def add(ctx, symbol: str, shares: int):
    symbol = symbol.upper()
    update_db("INSERT INTO portfolios (user_id, symbol, shares) VALUES (?, ?, ?)", 
              (ctx.author.id, symbol, shares))
    await ctx.send(f"✅ יהונתן, הוספתי {shares} מניות של {symbol} לתיק שלך!")

@bot.command()
async def portfolio(ctx):
    data = fetch_db("SELECT symbol, SUM(shares) FROM portfolios WHERE user_id = ? GROUP BY symbol", (ctx.author.id,))
    if not data:
        await ctx.send("📪 התיק שלך ריק.")
        return
    
    msg = f"📋 **התיק של {ctx.author.name}:**\n"
    for symbol, shares in data:
        price, _ = get_stock_data(symbol)
        msg += f"🔹 {symbol}: {shares} מניות (מחיר נוכחי: ${price})\n"
    await ctx.send(msg)

@tasks.loop(minutes=5)
async def check_alerts():
    # כאן יבוא הקוד של ההתראות שמושך נתונים מהמסד (באותו עיקרון)
    pass

bot.run(os.environ.get('DISCORD_TOKEN'))
