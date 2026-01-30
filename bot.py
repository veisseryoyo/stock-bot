import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread

# --- מעקף Health Check עבור Koyeb ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run_flask():
    # Koyeb משתמש בפורט 8080 כברירת מחדל ב-Web Service
    app.run(host='0.0.0.0', port=8000)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
# ----------------------------------

# הגדרות הבוט
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# פונקציה למשיכת מחיר מנייה (Yahoo Finance)
def get_stock_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        change = res['chart']['result'][0]['meta']['chartPreviousClose']
        p_change = ((price - change) / change) * 100
        return round(price, 2), round(p_change, 2)
    except:
        return None, None

@bot.event
async def on_ready():
    print(f'✅ הבוט {bot.user.name} מחובר ומוכן לעזור ליהונתן!')

# פקודה 1: בדיקת מחיר מניה כללית
@bot.command()
async def stock(ctx, symbol: str):
    price, change = get_stock_price(symbol)
    if price:
        emoji = "📈" if change >= 0 else "📉"
        await ctx.send(f"📊 **{symbol.upper()}**\n💰 מחיר: `${price}`\n{emoji} שינוי יומי: `{change}%`")
    else:
        await ctx.send(f"❌ לא הצלחתי למצוא נתונים עבור {symbol.upper()}.")

# פקודה 2: התיק האישי של יהונתן
@bot.command()
async def p(ctx):
    # נתונים עבור AT&T (T) כפי שביקשת
    price, change = get_stock_price("T")
    if price:
        shares = 24
        total_value = price * shares
        # נניח מחיר קנייה ממוצע של 22.00 דולר
        profit_loss = (price - 22.00) * shares 
        
        embed = discord.Embed(title="💼 המנהל הפיננסי של יהונתן", color=0x2ecc71 if change >= 0 else 0xe74c3c)
        embed.add_field(name="מנייה", value="AT&T (T)", inline=True)
        embed.add_field(name="מחיר נוכחי", value=f"${price}", inline=True)
        embed.add_field(name="כמות מניות", value=str(shares), inline=True)
        embed.add_field(name="💰 שווי כולל", value=f"${total_value:,.2f}", inline=False)
        embed.add_field(name="📈 רווח/הפסד כולל (משוער)", value=f"${profit_loss:,.2f}", inline=True)
        
        embed.set_footer(text="הנתונים נמשכים בזמן אמת מ-Yahoo Finance")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ תקלה במשיכת נתוני התיק.")

# הפעלה
if __name__ == "__main__":
    keep_alive() # מפעיל את השרת שמונע מ-Koyeb לכבות את הבוט
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        bot.run(token)
    else:
        print("❌ שגיאה: לא נמצא DISCORD_TOKEN במשתני הסביבה!")
