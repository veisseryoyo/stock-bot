import discord
from discord.ext import commands, tasks
import requests
import os
import psycopg2 # ספרייה לחיבור למסד הנתונים החדש
import urllib.parse
from flask import Flask
from threading import Thread

# --- הגדרת Flask עבור Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_flask(): app.run(host='0.0.0.0', port=8000)

# --- חיבור למסד הנתונים PostgreSQL (Supabase) ---
DATABASE_URL = "postgresql://postgres:[Yםטםה130113!]@db.fjgheilfootqypbqxiks.supabase.co:5432/postgres"

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    # יצירת טבלאות בפורמט PostgreSQL
    c.execute('''CREATE TABLE IF NOT EXISTS portfolios 
                 (user_id BIGINT, symbol TEXT, shares INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (user_id BIGINT, symbol TEXT, target_price REAL)''')
    conn.commit()
    c.close()
    conn.close()

def db_execute(query, params):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    c.close()
    conn.close()

def db_fetch(query, params=()):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute(query, params)
    res = c.fetchall()
    c.close()
    conn.close()
    return res

# --- פונקציות מניות ---
def get_stock_details(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=7d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        price = result['meta']['regularMarketPrice']
        prev_close = result['meta']['chartPreviousClose']
        change = ((price - prev_close) / prev_close) * 100
        history = [round(x, 2) for x in result['indicators']['quote'][0]['close'] if x is not None]
        return {"price": round(price, 2), "change": round(change, 2), "history": history}
    except: return None

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    init_db()
    if not check_alerts.is_running():
        check_alerts.start()
    print(f'✅ הבוט של {bot.user.name} מחובר ל-Supabase!')

@bot.command()
async def add(ctx, symbol: str, shares: int):
    symbol = symbol.upper()
    db_execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (%s, %s, %s)", 
               (ctx.author.id, symbol, shares))
    await ctx.send(f"✅ יהונתן, המניה {symbol} נשמרה ב-Supabase!")

@bot.command()
async def my_p(ctx):
    data = db_fetch("SELECT symbol, SUM(shares) FROM portfolios WHERE user_id = %s GROUP BY symbol", (ctx.author.id,))
    if not data:
        await ctx.send("📪 התיק שלך ריק.")
        return
    
    total_val = 0
    embed = discord.Embed(title=f"💼 התיק של יהונתן", color=0x3498db)
    for sym, shares in data:
        d = get_stock_details(sym)
        if d:
            v = d['price'] * shares
            total_val += v
            embed.add_field(name=f"{sym} ({shares})", value=f"${v:,.2f}", inline=False)
    
    embed.add_field(name='💰 סה"כ', value=f'**${total_val:,.2f}**', inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def stock(ctx, symbol: str):
    data = get_stock_details(symbol)
    if data:
        symbol = symbol.upper()
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol}',data:{data['history']},borderColor:'green'}}]}}}}"
        encoded = urllib.parse.quote(chart_config)
        chart_url = f"https://quickchart.io/chart?c={encoded}"
        
        embed = discord.Embed(title=f"📊 מניית {symbol}", color=0x2ecc71)
        embed.add_field(name="מחיר", value=f"${data['price']}", inline=True)
        embed.set_image(url=chart_url)
        await ctx.send(embed=embed)

@tasks.loop(minutes=10)
async def check_alerts():
    # קוד התראות...
    pass

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(os.environ.get('DISCORD_TOKEN'))
