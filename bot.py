import discord
from discord.ext import commands
import requests
import os
import psycopg2
import urllib.parse
from flask import Flask
from threading import Thread

# --- Flask ל-Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- פונקציה לחיבור למסד הנתונים החדש ---
def get_db_connection():
    return psycopg2.connect(
        host="db.ouuieanhljwxiqlljwtv.supabase.co",
        database="postgres",
        user="postgres",
        password="Yoyov130113!", # הסיסמה החדשה שלך
        port="5432"
    )

def db_execute(query, params):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

def db_fetch(query, params=()):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ הבוט מחובר למסד החדש!')

@bot.command()
async def add(ctx, symbol: str, shares: int):
    try:
        symbol = symbol.upper()
        db_execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (%s, %s, %s)", 
                   (ctx.author.id, symbol, shares))
        await ctx.send(f"✅ יהונתן, שמרתי {shares} מניות של {symbol} ב-Supabase החדש!")
    except Exception as e:
        await ctx.send(f"❌ שגיאה: {e}")

@bot.command()
async def my_p(ctx):
    try:
        data = db_fetch("SELECT symbol, SUM(shares) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
        if not data:
            await ctx.send("📪 התיק שלך ריק.")
            return
        msg = "💼 **התיק השמור שלך:**\n"
        for sym, shares in data:
            msg += f"🔹 {sym}: {shares} יחידות\n"
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"❌ שגיאה בשליפה: {e}")

@bot.command()
async def stock(ctx, symbol: str):
    symbol = symbol.upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        
        # יצירת גרף מהיר
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5],datasets:[{{label:'{symbol}',data:[{price-0.1},{price-0.05},{price},{price+0.05}],borderColor:'green'}}]}}}}"
        encoded = urllib.parse.quote(chart_config)
        
        embed = discord.Embed(title=f"📊 מניית {symbol}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${price}")
        embed.set_image(url=f"https://quickchart.io/chart?c={encoded}")
        await ctx.send(embed=embed)
    except:
        await ctx.send(f"📈 המחיר של {symbol} הוא כרגע לא זמין, נסה שוב.")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
