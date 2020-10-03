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


def userHasScoreReporterRole(user, db):
    if user.server_permissions.administrator:
        return True

    reportRolesCollection = db[REPORT_ROLES_COLLECTION]
    roles = reportRolesCollection.find({})

    if not roles:
        return False

    for role in roles[ROLES_KEY]:
        if user.roles.find(roles) != -1:
            return True

    return False


def userHasAdminRole(user):
    return user.guild_permissions.administrator


@bot.event
async def on_ready():
    for guild in bot.guilds:
        print(guild.name)
        async for member in guild.fetch_members():
            print(member.name + " " + str(member.id))


# TODO: Test and ensure that non-admins can't call this
@bot.command(name="toggleReportRole",
             help="This command (only callable by server admins) adds a role to the list of roles "
                  "that can report scores if not present, or it removes the role from the list if "
                  "it is already there.",
             usage="addReportRole RoleName",
             aliases=["ToggleReportRole", "togglereportrole"])
async def toggleReportRole(ctx, roleName: str):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

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
        roles += [roleName]
        collection.update_one({}, {"$set": {ROLES_KEY: roles}})
        message = f"The role *{roleName}* has been added to the list of roles that can report scores"
        await ctx.send(message)
    else:
        roles.remove(roleName)
        collection.update_one({}, {"$set": {ROLES_KEY: roles}})
        message = f"The role *{roleName}* has been removed from the list of roles that can report scores"
        await ctx.send(message)


@bot.command(name='leaderboard',
             help="Displays the ranked leaderboard for this server",
             usage="leaderboard",
             aliases=["Leaderboard", "LeaderBoard"])
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


@bot.command(name='adjust',
             help="Manually adjusts the score of the mentioned player. Can only be called by members with roles that "
                  "can report scores.",
             usage="adjust <@Member> <PointChange>",
             aliases=["Adjust", "adjustPoints", "AdjustPoints", "adjustpoints"])
async def adjustPoints(ctx, mention: str, points: float):
    playerId = getIDFromMention(mention)
    db = cluster[str(ctx.guild.id)]

    if not userHasScoreReporterRole(ctx.message.author, db):
        await ctx.send("You are not a score reporter for the ranked bot!")
        return

    collection = db[PLAYER_DATA_COLLECTION]
    collection.find_one_and_update({ID_KEY: playerId}, {"$inc": {POINTS_KEY: points}}, upsert=True)

    pointWord = "point" if abs(points) == 1 else "points"
    member = await ctx.guild.fetch_member(int(playerId))
    name = member.display_name
    message = f"{name} has earned {points} {pointWord}!" if points > 0 else f"{name} has lost {-points} {pointWord}."

    await ctx.send(message)


# TODO: Get some more error testing in, but this can likely be done after ppl use it and see how it goes
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        message = f"Be sure you use all required arguments! \nThe correct usage is: `{ctx.bot.command_prefix}" \
                  f"{ctx.command.usage}` "
        await ctx.send(message)


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
