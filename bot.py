import os

import pymongo
from pymongo import MongoClient

from discord.ext import commands
from dotenv import load_dotenv

bot = commands.Bot(command_prefix='!')
load_dotenv()
cluster = MongoClient(os.getenv('MONGO_DB_URL'))

TOKEN = os.getenv('DISCORD_TOKEN')

PLAYER_DATA_COLLECTION = "player_data"
REPORT_ROLES_COLLECTION = "report_roles"

ID_KEY = "_id"
POINTS_KEY = "points"
ROLES_KEY = "roles"


def getIDFromMention(mention):
    userId = ""
    for char in mention:
        if char.isdigit():
            userId += char
    return userId


#TODO: limit use of non-leaderboard features to only roles in the list (unless it's empty)

# def userHasDesignatedRole(user, db):
#     configCollection = db[CONFIG_DATA_COLLECTION]
#     configFile = configCollection.find({})
#
#     if not configFile or not configFile[REPORT_ROLES_KEY]:
#         return True
#
#     for role in configFile[REPORT_ROLES_KEY]:
#         if user.roles.find()


@bot.event
async def on_ready():
    for guild in bot.guilds:
        print(guild.name)
        async for member in guild.fetch_members():
            print(member.name + " " + str(member.id))


@bot.command(name="ReportRole")
async def toggleReportRole(ctx, roleName: str):
    db = cluster[str(ctx.guild.id)]
    collection = db[REPORT_ROLES_COLLECTION]
    configFile = collection.find_one({})

    print(configFile)
    if not configFile:
        collection.insert_one({ROLES_KEY: [roleName]})
        message = f"The role *{roleName}* has been added to the list of roles that can report scores"
        await ctx.send(message)
        return

    roles = configFile[ROLES_KEY]

    if roleName not in roles:
        roles += roleName
        collection.update_one({}, {"$set": {ROLES_KEY: roles}})
        message = f"The role *{roleName}* has been added to the list of roles that can report scores"
        await ctx.send(message)
    else:
        roles.remove(roleName)
        collection.update_one({}, {"$set": {ROLES_KEY: roles}})
        message = f"The role *{roleName}* has been removed from the list of roles that can report scores"
        await ctx.send(message)


@bot.command(name='leaderboard')
async def displayLeaderboard(ctx):
    leaderboard = []

    def getPoints(lst):
        return lst[1]

    db = cluster[str(ctx.guild.id)]
    collection = db[PLAYER_DATA_COLLECTION]
    data = collection.find({})
    print(data)

    for entry in data:
        user = await ctx.guild.fetch_member(int(entry[ID_KEY]))
        if user is not None:
            leaderboard.append([user.display_name, entry["points"]])
            print(user.display_name)

    message = ""
    rank = 0
    leaderboard.sort(key=getPoints, reverse=True)

    for person in leaderboard:
        rank += 1
        message += "\n" + str(rank) + ". " + person[0] + " (" + str(person[1]) + ")"

    await ctx.send(message)


@bot.command(name='adjust')
async def adjustPoints(ctx, mention: str, points: float):
    playerId = getIDFromMention(mention)
    db = cluster[str(ctx.guild.id)]
    collection = db[PLAYER_DATA_COLLECTION]
    collection.find_one_and_update({ID_KEY: playerId}, {"$inc": {POINTS_KEY: points}}, upsert=True)

    pointWord = "point" if abs(points) == 1 else "points"
    member = await ctx.guild.fetch_member(int(playerId))
    name = member.display_name
    message = f"{name} has earned {points} {pointWord}!" if points > 0 else f"{name} has lost {-points} {pointWord}."

    await ctx.send(message)

#TODO: Make the error handling more specific based on the attempted command
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send('Be sure you use all required arguments')


bot.run(TOKEN)


""" EXPECTED DATA STRUCTURE
DATABASE:
    SERVER COLLECTION 1:
        Config:
            - Roles allowed for use
        User:
            - Id
            - Points
    SERVER COLLECTION 2:
    ...
"""