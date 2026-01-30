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

# --- חיבור למסד הנתונים (הפרדה למניעת שגיאות סיסמה) ---
def get_db_connection():
    # הקישור ששלחת, מפורק כדי שפייתון יבין אותו נכון
    conn = psycopg2.connect(
        host="db.fjgheilfootqypbqxiks.supabase.co",
        database="postgres",
        user="postgres",
        password="Yםטםה130113!", # הסיסמה שלך נקייה
        port="5432"
    )
    return conn

# --- פונקציות עזר ---
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
    print(f'✅ הבוט של יהונתן מחובר!')

@bot.command()
async def add(ctx, symbol: str, shares: int):
    try:
        symbol = symbol.upper()
        db_execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (%s, %s, %s)", 
                   (ctx.author.id, symbol, shares))
        await ctx.send(f"✅ שמרתי {shares} מניות של {symbol} ב-Supabase!")
    except Exception as e:
        await ctx.send(f"❌ שגיאת מסד נתונים: {e}")

@bot.command()
async def stock(ctx, symbol: str):
    # פקודת הסטוק המוכרת שלך...
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=7d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers).json()
    price = res['chart']['result'][0]['meta']['regularMarketPrice']
    await ctx.send(f"📈 המחיר של {symbol.upper()} הוא ${price}")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
