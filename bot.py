import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# --- מעקף Koyeb (Port 8000) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Running!"
def run_flask(): app.run(host='0.0.0.0', port=8000)
def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# תיק השקעות ברירת מחדל
my_portfolio = {'T': 24} 

def get_detailed_stock(symbol):
    # משיכת נתונים מורחבים כולל היסטוריה לגרף
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=7d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        price = result['meta']['regularMarketPrice']
        prev_close = result['meta']['chartPreviousClose']
        change = ((price - prev_close) / prev_close) * 100
        
        # הכנת נתונים לגרף
        history = result['indicators']['quote'][0]['close']
        history = [round(x, 2) for x in history if x is not None]
        
        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "history": history,
            "currency": result['meta']['currency']
        }
    except:
        return None

def create_graph_url(symbol, history):
    # יצירת גרף ויזואלי באמצעות QuickChart API
    labels = ["" for _ in history] # תוויות ריקות למראה נקי
    data_str = ",".join(map(str, history))
    color = "00ff00" if history[-1] >= history[0] else "ff0000"
    
    chart_config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": symbol.upper(),
                "data": history,
                "fill": True,
                "backgroundColor": f"rgba({int(color[:2],16)}, {int(color[2:4],16)}, {int(color[4:],16)}, 0.1)",
                "borderColor": f"#{color}",
                "pointRadius": 0
            }]
        },
        "options": {
            "title": {"display": True, "text": f"7-Day Trend: {symbol.upper()}"},
            "legend": {"display": False}
        }
    }
    encoded_config = str(chart_config).replace(" ", "")
    return f"https://quickchart.io/chart?c={encoded_config}&width=500&height=300"

@bot.event
async def on_ready():
    print(f'✅ המערכת הפיננסית של יהונתן באוויר (Port 8000)')

@bot.command()
async def stock(ctx, symbol: str):
    data = get_detailed_stock(symbol)
    if data:
        color = 0x2ecc71 if data['change'] >= 0 else 0xe74c3c
        embed = discord.Embed(title=f"📊 ניתוח מניית {symbol.upper()}", color=color)
        embed.add_field(name="💰 מחיר", value=f"${data['price']} {data['currency']}", inline=True)
        embed.add_field(name="📈 שינוי", value=f"{data['change']}%", inline=True)
        
        # הוספת גרף
        graph_url = create_graph_url(symbol, data['history'])
        embed.set_image(url=graph_url)
        
        # לינקים לחדשות
        embed.add_field(name="📰 חדשות", value=f"[לחץ כאן לחדשות {symbol.upper()}](https://finance.yahoo.com/quote/{symbol})", inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ לא מצאתי נתונים עבור {symbol.upper()}.")

@bot.command()
async def p(ctx):
    embed = discord.Embed(title="💼 תיק ההשקעות של יהונתן", color=0x9b59b6)
    total_value = 0
    
    for symbol, shares in my_portfolio.items():
        data = get_detailed_stock(symbol)
        if data:
            val = data['price'] * shares
            total_value += val
            embed.add_field(
                name=f"{symbol.upper()} ({shares} יחידות)", 
                value=f"שווי: `${val:,.2f}` ({data['change']}%)", 
                inline=False
            )
    
    embed.add_field(name="💰 סה\"כ שווי תיק", value=f"**${total_value:,.2f}**", inline=False)
    embed.set_footer(text=f"עודכן ב: {datetime.now().strftime('%H:%M:%S')}")
    await ctx.send(embed=embed)

@bot.command()
async def add(ctx, symbol: str, shares: int):
    my_portfolio[symbol.upper()] = my_portfolio.get(symbol.upper(), 0) + shares
    await ctx.send(f"✅ נוספו {shares} מניות של {symbol.upper()} לתיק.")

@bot.command()
async def h(ctx):
    msg = (
        "**מפקדת הבוט של יהונתן:**\n"
        "`!stock [T/AAPL/NVDA]` - מחיר + גרף שבועי\n"
        "`!p` - מצב התיק האישי שלך\n"
        "`!add [סמל] [כמות]` - הוספה לתיק\n"
    )
    await ctx.send(msg)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get('DISCORD_TOKEN'))
