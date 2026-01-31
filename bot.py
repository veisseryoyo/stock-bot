# --- פונקציות נתונים חדשות ---
def get_market_indices():
    indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI"}
    results = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, sym in indices.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
            res = requests.get(url, headers=headers).json()
            meta = res['chart']['result'][0]['meta']
            change = ((meta['regularMarketPrice'] - meta['chartPreviousClose']) / meta['chartPreviousClose']) * 100
            results[name] = {"price": meta['regularMarketPrice'], "change": change}
        except: continue
    return results

# --- פקודות חדשות לבוט ---

@bot.command()
async def market(ctx):
    """תמונת מצב של השווקים בעולם"""
    indices = get_market_indices()
    embed = discord.Embed(title="🌍 תמונת מצב שוק עולמי", color=0x9b59b6)
    for name, data in indices.items():
        emoji = "🟢" if data['change'] >= 0 else "🔴"
        embed.add_field(name=name, value=f"{emoji} {data['price']:,.2f} ({data['change']:.2f}%)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def convert(ctx, amount: float, symbol: str):
    """כמה שווה X מניות בדולרים? לדוגמה: !convert 10 T"""
    data = get_data(symbol)
    if data:
        total = amount * data['price']
        await ctx.send(f"💰 {amount} יחידות של {symbol.upper()} שוות כרגע **${total:,.2f}**")
    else:
        await ctx.send("❌ לא מצאתי את המניה.")

@bot.command()
async def calc(ctx, budget: float, symbol: str):
    """כמה מניות אני יכול לקנות בתקציב מסוים? לדוגמה: !calc 5000 TSLA"""
    data = get_data(symbol)
    if data:
        count = budget / data['price']
        await ctx.send(f"🛍️ עם תקציב של **${budget:,.2f}**, אתה יכול לקנות **{count:.2f}** מניות של {symbol.upper()}.")
    else:
        await ctx.send("❌ לא מצאתי את המניה.")

@bot.command()
async def top_movers(ctx):
    """מציג מניות חמות לחיפוש מהיר"""
    # רשימת מניות פופולריות לבדיקה מהירה
    popular = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "GOOGL", "META"]
    movers = []
    for s in popular:
        d = get_data(s)
        if d:
            change = ((d['price'] - d['prev']) / d['prev']) * 100
            movers.append({"sym": s, "change": change})
    
    movers.sort(key=lambda x: abs(x['change']), reverse=True)
    embed = discord.Embed(title="🔥 המניות הכי תנודתיות היום", color=0xe67e22)
    for m in movers[:5]:
        emoji = "📈" if m['change'] >= 0 else "📉"
        embed.add_field(name=m['sym'], value=f"{emoji} {m['change']:.2f}%", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def help_me(ctx):
    """מדריך פקודות לבוט של יהונתן"""
    msg = """
**🤖 פקודות הבוט הפיננסי של יהונתן:**
`!stock [SYM]` - מחיר נוכחי + גרף
`!crypto [SYM]` - מחיר קריפטו (BTC, ETH...)
`!add [SYM] [כמות] [מחיר]` - הוספה לתיק השמור
`!my_p` - הצגת תיק ההשקעות ורווח/הפסד
`!news [SYM]` - חדשות אחרונות
`!market` - מצב המדדים המובילים (S&P 500...)
`!calc [תקציב] [SYM]` - כמה אפשר לקנות ב-$
`!convert [כמות] [SYM]` - שווי המניות ב-$
    """
    await ctx.send(msg)
