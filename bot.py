import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread
from datetime import datetime

# --- מעקף Koyeb (Port 8000) ---
app = Flask('')
@app.route('/')
def home(): return "Financial System Online"
def run_flask(): app.run(host='0.0.0.0', port=8000)
def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

my_portfolio = {'T': 24} 

def get_detailed_data(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=7d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        price = result['meta']['regularMarketPrice']
        prev_close = result['meta']['chartPreviousClose']
        change = ((price - prev_close) / prev_close) * 100
        history = result['indicators']['quote'][0]['close']
        history = [round(x, 2) for x in history if x is not None]
        return {"price": round(price, 2), "change": round(change, 2), "history": history, "currency": result['meta']['currency']}
    except: return None

def get_graph_url(symbol, history):
    color = "00ff00" if history[-1] >= history[0] else "ff0000"
    chart_config = {
        "type": "line",
        "data": {
            "labels": ["" for _ in history],
            "datasets": [{"data": history, "borderColor": f"#{color}", "fill": False, "pointRadius": 3}]
        },
        "options": {"title": {"display": True, "text": f"{symbol.upper()} - 7 Day Trend"}, "legend": {"display": False}}
    }
    return f"https://quickchart.io/chart?c={str(chart_config).replace(' ', '')}&width=400&height=200"

@bot.event
async def on_ready():
    print('✅ המערכת של יהונתן מוכנה!')

@bot.command()
async def stock(ctx, symbol: str):
    data = get_detailed_data(symbol)
    if data:
        color = 0x2ecc71 if data['change'] >= 0 else 0xe74c3c
        embed = discord.Embed(title=f"📊 ניתוח מניית {symbol.upper()}", color=color)
        embed.add_field(name="💰 מחיר", value=f"${data['price']} {data['currency']}", inline=True)
        embed.add_field(name="📈 שינוי", value=f"{data['change']}%", inline=True)
        embed.set_image(url=get_graph_url(symbol, data['history']))
        embed.add_field(name="📰 חדשות", value=f"[לחדשות האחרונות](https://finance.yahoo.com/quote/{symbol})", inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ לא מצאתי נתונים עבור {symbol.upper()}.")

@bot.command()
async def p(ctx):
    embed = discord.Embed(title="💼 תיק ההשקעות של יהונתן", color=0x3498db)
    total_value = 0
    for symbol, shares in my_portfolio.items():
        data = get_detailed_data(symbol)
        if data:
            val = data['price'] * shares
            total_value += val
            embed.add_field(name=f"{symbol.upper()} ({shares} יחידות)", value=f"שווי: ${val:,.2f} | שינוי: {data['change']}%", inline=False)
    
    # כאן היה התיקון - שימוש בגרש בודד למניעת שגיאת סינטקס
    embed.add_field(name='💵 סה"כ שווי בדולר', value=f'**${total_value:,.2f}**', inline=False)
    embed.set_footer(text=f"עודכן ב: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    await ctx.send(embed=embed)

@bot.command()
async def add(ctx, symbol: str, shares: int):
    symbol = symbol.upper()
    my_portfolio[symbol] = my_portfolio.get(symbol, 0) + shares
    await ctx.send(f"✅ יהונתן, הוספתי {shares} מניות של **{symbol}** לתיק!")

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get('DISCORD_TOKEN'))
