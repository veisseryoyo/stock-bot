import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread

# --- מעקף Koyeb ---
app = Flask('')
@app.route('/')
def home(): return "I am alive!"
def run_flask(): app.run(host='0.0.0.0', port=8000)
def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- הגדרות בוט ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# "זיכרון" זמני (בגרסה הבאה נחבר מסד נתונים קבוע)
# פורמט: { 'מניה': כמות }
my_portfolio = {'T': 24} 

def get_stock_info(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        price = meta['regularMarketPrice']
        prev_close = meta['chartPreviousClose']
        change = ((price - prev_close) / prev_close) * 100
        return round(price, 2), round(change, 2)
    except:
        return None, None

@bot.event
async def on_ready():
    print(f'✅ המערכת של יהונתן באוויר!')

# פקודה 1: הצגת התיק המלא
@bot.command()
async def p(ctx):
    embed = discord.Embed(title="🚀 המנהל הפיננסי של יהונתן", color=0x3498db)
    total_portfolio_value = 0
    
    for symbol, shares in my_portfolio.items():
        price, change = get_stock_info(symbol)
        if price:
            value = price * shares
            total_portfolio_value += value
            emoji = "🟢" if change >= 0 else "🔴"
            embed.add_field(
                name=f"{symbol.upper()} ({shares} יחידות)", 
                value=f"מחיר: `${price}` | שינוי: `{change}%` {emoji}\nשווי: `${value:,.2f}`", 
                inline=False
            )
    
    embed.add_field(name="💰 שווי תיק כולל", value=f"**${total_portfolio_value:,.2f}**", inline=False)
    
    # "ניתוח חכם"
    if total_portfolio_value > 0:
        advice = "התיק נראה יציב! כדאי להמשיך לעקוב." if total_portfolio_value > 500 else "זמן טוב להגדיל השקעות?"
        embed.set_footer(text=f"ניתוח AI: {advice}")
        
    await ctx.send(embed=embed)

# פקודה 2: הוספת מניה לתיק
@bot.command()
async def add(ctx, symbol: str, shares: int):
    symbol = symbol.upper()
    my_portfolio[symbol] = my_portfolio.get(symbol, 0) + shares
    await ctx.send(f"✅ יהונתן, הוספתי {shares} מניות של **{symbol}** לתיק שלך!")

# פקודה 3: הסרת מניה
@bot.command()
async def remove(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol in my_portfolio:
        del my_portfolio[symbol]
        await ctx.send(f"🗑️ המניה {symbol} הוסרה מהמעקב.")
    else:
        await ctx.send(f"❓ לא מצאתי את {symbol} בתיק שלך.")

# פקודה 4: עזרה
@bot.command()
async def h(ctx):
    help_text = (
        "**פקודות זמינות:**\n"
        "`!p` - הצגת התיק המלא שלך\n"
        "`!stock [מניה]` - בדיקת מחיר מהירה\n"
        "`!add [מניה] [כמות]` - הוספה לתיק\n"
        "`!remove [מניה]` - הסרה מהתיק"
    )
    await ctx.send(help_text)

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get('DISCORD_TOKEN'))
