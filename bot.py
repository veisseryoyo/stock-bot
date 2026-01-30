import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread
import urllib.parse  # ספרייה חדשה לתיקון הקישורים

# --- הגדרת פורט 8000 עבור Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
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

def get_stock_details(symbol):
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
        return {"price": round(price, 2), "change": round(change, 2), "history": history}
    except: return None

@bot.event
async def on_ready():
    print('✅ הבוט של יהונתן מחובר ומוכן לגרפים!')

@bot.command()
async def stock(ctx, symbol: str):
    data = get_stock_details(symbol)
    if data:
        symbol = symbol.upper()
        
        # יצירת הגדרות הגרף
        chart_config = f"{{type:'line',data:{{labels:[1,2,3,4,5,6,7],datasets:[{{label:'{symbol}',data:{data['history']},borderColor:'green',fill:false}}]}}}}"
        
        # התיקון הקריטי: הופך את הטקסט לקישור חוקי (URL Encoded)
        encoded_config = urllib.parse.quote(chart_config)
        chart_url = f"https://quickchart.io/chart?c={encoded_config}"
        
        embed = discord.Embed(title=f"📊 מניית {symbol}", color=0x2ecc71)
        embed.add_field(name="💰 מחיר", value=f"${data['price']}", inline=True)
        embed.add_field(name="📈 שינוי", value=f"{data['change']:.2f}%", inline=True)
        embed.set_image(url=chart_url)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ לא מצאתי נתונים עבור {symbol}")

@bot.command()
async def p(ctx):
    embed = discord.Embed(title="💼 התיק של יהונתן", color=0x3498db)
    total_val = 0
    for sym, shares in my_portfolio.items():
        d = get_stock_details(sym)
        if d:
            v = d['price'] * shares
            total_val += v
            embed.add_field(name=f"{sym} ({shares} יחידות)", value=f"שווי: ${v:,.2f}", inline=False)
    embed.add_field(name='💵 סה"כ שווי', value=f'**${total_val:,.2f}**', inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get('DISCORD_TOKEN'))
