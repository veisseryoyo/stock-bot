import discord
from discord.ext import commands
import requests
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# פונקציית משיכת נתונים מ-Yahoo Finance (חינמי וללא הגבלה)
def get_stock(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        return round(price, 2)
    except:
        return None

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} באוויר ומוכן לעזור ליהונתן!')

@bot.command()
async def stock(ctx, symbol):
    """בודק מחיר של כל מניה: !stock NVDA"""
    price = get_stock(symbol)
    if price:
        await ctx.send(f"📊 המחיר של **{symbol.upper()}** כרגע הוא: `${price}`")
    else:
        await ctx.send("❌ לא מצאתי את המניה הזו.")

@bot.command()
async def portfolio(ctx):
    """התיק האישי שלך: !portfolio"""
    price = get_stock("T")
    if price:
        total = price * 24
        await ctx.send(f"💼 **התיק של יהונתן (AT&T):**\n💰 מחיר: `${price}`\n📉 שווי כולל: `${total:,.2f}`")

bot.run(os.environ.get('DISCORD_TOKEN'))
