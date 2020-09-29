import os

import pymongo
from pymongo import MongoClient

from discord.ext import commands
from dotenv import load_dotenv

bot = commands.Bot(command_prefix='!')
load_dotenv()
cluster = MongoClient(os.getenv('MONGO_DB_URL'))
db = cluster["sample_analytics"]

TOKEN = os.getenv('DISCORD_TOKEN')


@bot.event
async def on_ready():
    for guild in bot.guilds:
        print(guild.name)


@bot.command(name='account')
async def on_message(ctx):
    collection = db[str(ctx.guild.id)]
    post = {"_id": ctx.author.id, "score": 1}
    collection.insert_one(post)
    await ctx.send("DONE")


bot.run(TOKEN)
