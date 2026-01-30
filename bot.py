import discord
from discord.ext import commands
import requests
import os
from flask import Flask
from threading import Thread

# --- חלק המעקף עבור Koyeb ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run_flask():
    # הבוט יקשיב בפורט 8000 ש-Koyeb מחפש
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()
# ---------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} באוויר!')

@bot.command()
async def portfolio(ctx):
    # הפונקציה המוכרת שלך
    await ctx.send(f"💼 יהונתן, התיק שלך בבדיקה...")

if __name__ == "__main__":
    keep_alive() # מפעיל את השרת שמרצה את ה-Health Check
    bot.run(os.environ.get('DISCORD_TOKEN'))
