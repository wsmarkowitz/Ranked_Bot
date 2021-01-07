import os

from pymongo import MongoClient

import discord
from discord.ext import commands
from dotenv import load_dotenv

import parseFormmula

load_dotenv()
cluster = MongoClient(os.getenv('MONGO_DB_URL'))

TOKEN = os.getenv('DISCORD_TOKEN')

PLAYER_DATA_COLLECTION = "player_data"
CONFIG_COLLECTION = "config"
PENDING_RESULTS_COLLECTION = "pending_results"

ID_KEY = "_id"
POINTS_KEY = "points"

# REPORT_ROLES_KEY = "report_roles"
# DEFAULT_REPORT_ROLES = []

TIERS_KEY = "tiers"
DEFAULT_TIERS = {}

POINTS_GAINED_FORMULA_KEY = "points_gained_formula"
DEFAULT_POINTS_GAINED_FORMULA = "5 + ( -1 * POINT_DIFFERENCE / 8 )"

MIN_POINTS_GAINED_KEY = "min_points_gained"
DEFAULT_MIN_POINTS_GAINED = 1

MAX_POINTS_GAINED_KEY = "max_points_gained"
DEFAULT_MAX_POINTS_GAINED = 20

POINTS_LOST_FORMULA_KEY = "points_lost_formula"
DEFAULT_POINTS_LOST_FORMULA = "5 + ( -1 * POINT_DIFFERENCE / 8 )"

MIN_POINTS_LOST_KEY = "min_points_lost"
DEFAULT_MIN_POINTS_LOST = 1

MAX_POINTS_LOST_KEY = "max_points_lost"
DEFAULT_MAX_POINTS_LOST = 20

COMMAND_PREFIX_KEY = "command_prefix"
DEFAULT_COMMAND_PREFIX = "!"

INITIAL_CONFIG_FILE = {
    # REPORT_ROLES_KEY: DEFAULT_REPORT_ROLES,
    COMMAND_PREFIX_KEY: DEFAULT_COMMAND_PREFIX,
    TIERS_KEY: DEFAULT_TIERS,
    POINTS_GAINED_FORMULA_KEY: DEFAULT_POINTS_GAINED_FORMULA,
    POINTS_LOST_FORMULA_KEY: DEFAULT_POINTS_LOST_FORMULA,
    MIN_POINTS_GAINED_KEY: DEFAULT_MIN_POINTS_GAINED,
    MAX_POINTS_GAINED_KEY: DEFAULT_MAX_POINTS_GAINED,
    MIN_POINTS_LOST_KEY: DEFAULT_MIN_POINTS_LOST,
    MAX_POINTS_LOST_KEY: DEFAULT_MAX_POINTS_LOST,
}


def get_command_prefix(_, message):
    db = cluster[str(message.guild.id)]
    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    command_prefix = configFile[COMMAND_PREFIX_KEY]
    return command_prefix


intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix=get_command_prefix, intents=intents)


def getIDFromMention(mention):
    userId = ""
    for char in mention:
        if char.isdigit():
            userId += char
    return userId


# def userHasScoreReporterRole(user, db):
#     if user.guild_permissions.administrator:
#         return True
#
#     reportRolesCollection = db[CONFIG_COLLECTION]
#     roles = reportRolesCollection.find({})
#
#     if not roles:
#         return False
#
#     for role in roles[REPORT_ROLES_KEY]:
#         if user.roles.find(roles) != -1:
#             return True
#
#     return False


def userHasAdminRole(user):
    return user.guild_permissions.administrator


@bot.event
async def on_ready():
    for guild in bot.guilds:
        print(guild.name)
        async for member in guild.fetch_members():
            print(member.name + " " + str(member.id))


# TODO: Test and ensure that non-admins can't call this
@bot.command(name="changeCommandPrefix",
             help="This command changes the bot's command prefix. Only usable by server admins.",
             usage="changeCommandPrefix newCommandPrefix",
             aliases=["ChangeCommandPrefix", "changecommandprefix", "ChangeCommandprefix",
                      "changeCommandprefix", "ChangecommandPrefix, Changecommandprefix", "changecommandPrefix"])
async def changeCommandPrefix(ctx, command_prefix: str):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

    collection = db[CONFIG_COLLECTION]
    collection.update_one({}, {"$set": {COMMAND_PREFIX_KEY: command_prefix}})
    message = f"The command prefix has been set to `{command_prefix}`!"
    await ctx.send(message)


@bot.command(name="pointsGained",
             help="Set the formula for when you gain points for a win. Any singular mathematical expression will "
                  "suffice. The supported symbols are '+', '-', '*', '/', '(', ')', 'TIER_DIFFERENCE', "
                  "'POINT_DIFFERENCE', and 'PLACEMENT_DIFFERENCE'. Be sure to use a space between every symbol. "
                  "TIER_DIFFERENCE indicates how many tiers the winner is above the loser. POINT_DIFFERENCE indicates "
                  "how many more points the winner has over the loser. PLACEMENT_DIFFERENCE indicates how many places "
                  "the winner is above the loser on the leaderboard. An example formula would be `5 + ( -1 * POINT_DIFFERENCE / 8 )`.",
             usage='pointsGained "formula" minPointsGained (optional) maxPointsGained (optional)'
             )
async def pointsGainedFomula(ctx, formula: str, minRange=None, maxRange=None):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

    try:
        parseFormmula.evaluateFormula(formula, 0, 0, 0)
    except SyntaxError as e:
        await ctx.send(e)
        return

    collection = db[CONFIG_COLLECTION]

    collection.update_one({}, {"$set": {POINTS_GAINED_FORMULA_KEY: formula}})
    message = f"The pointsGained info has been changed: ```Formula: {formula}"

    if minRange:
        minPoints = float(minRange) if minRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
        collection.update_one({}, {"$set": {MIN_POINTS_GAINED_KEY: minPoints}})
        print(minPoints)
        message += "\nMinimum Points " + str(minPoints)
        print(message)

    if maxRange:
        maxPoints = float(maxRange) if maxRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
        collection.update_one({}, {"$set": {MAX_POINTS_GAINED_KEY: maxPoints}})
        message += "\nMaximum Points " + str(maxPoints)

    message += "```"
    await ctx.send(message)


@bot.command(name="pointsLost",
             help="Set the formula for when you gain points for a win. Any singular mathematical expression will "
                  "suffice. The supported symbols are '+', '-', '*', '/', '(', ')', 'TIER_DIFFERENCE', "
                  "'POINT_DIFFERENCE', and 'PLACEMENT_DIFFERENCE'. Be sure to use a space between every symbol. "
                  "TIER_DIFFERENCE indicates how many tiers the winner is above the loser. POINT_DIFFERENCE indicates "
                  "how many more points the winner has over the loser. PLACEMENT_DIFFERENCE indicates how many places "
                  "the winner is above the loser on the leaderboard. An example formula would be `5 + ( -1 * POINT_DIFFERENCE / 8 )`. "
                  "\n \n This should be a positive number, as this number will be subtracted from the loser's point total.",
             usage='pointsLost "formula" minPointsLost (optional) maxPointsLost (optional)'
             )
async def pointsLostFomula(ctx, formula: str, minRange=None, maxRange=None):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

    try:
        parseFormmula.evaluateFormula(formula, 0, 0, 0)
    except SyntaxError as e:
        await ctx.send(e)
        return

    collection = db[CONFIG_COLLECTION]

    collection.update_one({}, {"$set": {POINTS_LOST_FORMULA_KEY: formula}})
    message = f"The pointsLost info has been changed: ```Formula: {formula}"

    if minRange:
        minPoints = float(minRange) if minRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
        collection.update_one({}, {"$set": {MIN_POINTS_LOST_KEY: minPoints}})
        print(minPoints)
        message += "\nMinimum Points " + str(minPoints)
        print(message)

    if maxRange:
        maxPoints = float(maxRange) if maxRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
        collection.update_one({}, {"$set": {MAX_POINTS_LOST_KEY: maxPoints}})
        message += "\nMaximum Points " + str(maxPoints)

    message += "```"
    await ctx.send(message)


@bot.command(name="setTier",
             usage="setTier roleName points",
             help="Be sure the role name already is an existing role before using this command. "
                  "Also note that the number of points is the lower bound for reaching this tier/rank.",
             aliases=["settier", "SetTier", "Settier"])
async def setTier(ctx, roleName: str, points: float):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

    if not [True for role in ctx.guild.roles if role.name == roleName]:
        await ctx.send("That is not a valid role on this server! Remember that this is case sensitive!")
        return

    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    print(configFile)

    tiers = {}
    if TIERS_KEY in configFile.keys():
        tiers = configFile[TIERS_KEY]
    print(tiers)

    tiers[roleName] = points
    collection.update_one({}, {"$set": {TIERS_KEY: tiers}})
    message = f"The tier *{roleName}* now requires at least *{points}* points."
    await ctx.send(message)


@bot.command(name="removeTier",
             usage="removeTier roleName",
             help="Be sure the role name already is currently set before removing",
             aliases=["removetier", "RemoveTier", "Removetier"])
async def removeTier(ctx, roleName: str):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not an admin for the ranked bot!")
        return

    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    if not configFile[TIERS_KEY]:
        await ctx.send("That is not a role already set! Remember that this is case sensitive!")
        return
    keys = list(configFile[TIERS_KEY].keys())
    indices = range(len(keys))
    print(keys)
    matchingIndices = [index for index in indices if keys[index] == roleName]
    print(matchingIndices)
    if len(matchingIndices) == 0:
        await ctx.send("That is not a role already set! Remember that this is case sensitive!")
        return

    matchingIndex = matchingIndices[0]
    del configFile[TIERS_KEY][keys[matchingIndex]]
    collection.update_one({}, {"$set": {TIERS_KEY: configFile[TIERS_KEY]}})
    message = f"The tier *{roleName}* has been removed."
    await ctx.send(message)


@bot.command(name="viewTiers",
             usage="viewTiers",
             help="Displays the tier names and their minimum point values.",
             aliases=["viewtiers", "ViewTiers", "Viewtiers"])
async def viewTiers(ctx):
    sortedTiers = []

    def getPoints(lst):
        return lst[1]

    db = cluster[str(ctx.guild.id)]
    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})

    print(configFile)

    if not TIERS_KEY in configFile.keys():
        ctx.send("There are currently no tiers!")
        return
    tiers = configFile[TIERS_KEY]

    print(tiers)

    for key in tiers:
        sortedTiers.append([key, tiers[key]])

    message = "```TIER LISTING\n"
    sortedTiers.sort(key=getPoints, reverse=False)

    for tier in sortedTiers:
        message += "\n" + tier[0] + ": " + str(tier[1])

    message += "```"
    await ctx.send(message)


@bot.command(name='leaderboard',
             help="Displays the ranked leaderboard for this server.",
             aliases=["Leaderboard", "LeaderBoard", "leaderBoard"])
async def displayLeaderboard(ctx):
    leaderboard = []

    def getPoints(lst):
        return lst[1]

    db = cluster[str(ctx.guild.id)]
    collection = db[PLAYER_DATA_COLLECTION]
    data = list(collection.find({}))
    print(data)

    if not data:
        await ctx.send("There are current no players on the leaderboard!")

    for entry in data:
        # user = await ctx.guild.fetch_member(int(entry[ID_KEY]))
        user = ctx.guild.get_member(int(entry[ID_KEY]))
        print(user)
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


@bot.command(name='report',
             usage="report @winner, @loser",
             help="Report the reuslts of a set with this. Be sure to tag the winner first and the loser second. "
                  "Afterward, the bot will post a message for the players to confirm, at which point, "
                  "the resulting points will be adjusted.",
             aliases=["Report, results, Results, reportSet, ReportSet, reportset, Reportset"])
async def reportResult(ctx, winnerMention: str, loserMention: str):
    winner_id = str(getIDFromMention(winnerMention))
    loser_id = str(getIDFromMention(loserMention))

    guild = ctx.guild
    winnerTag = await guild.fetch_member(int(winner_id))
    loserTag = await guild.fetch_member(int(loser_id))

    message = f"{winnerTag} has beaten {loserTag}. React to this message if that is correct."

    sent_message = await ctx.send(message)
    db = cluster[str(ctx.guild.id)]
    collection = db[PENDING_RESULTS_COLLECTION]

    pendingResultDetails = {
        ID_KEY: sent_message.id,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "winner_confirmed": ctx.author.id == int(winner_id),
        "loser_confirmed": ctx.author.id == int(loser_id)
    }

    collection.insert_one(pendingResultDetails)
    await sent_message.add_reaction("✅")


@bot.command(name='adjust',
             help="Manually adjusts the score of the mentioned player. Can only be called by members with roles that "
                  "can report scores. Only usable by server admins.",
             usage="adjust <@Member> <PointChange>",
             aliases=["Adjust", "adjustPoints", "AdjustPoints", "adjustpoints"])
async def adjustPoints(ctx, mention: str, points: float):
    playerId = getIDFromMention(mention)
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        await ctx.send("You are not a score reporter for the ranked bot!")
        return

    collection = db[PLAYER_DATA_COLLECTION]
    collection.find_one_and_update({ID_KEY: playerId}, {"$inc": {POINTS_KEY: points}}, upsert=True)

    pointWord = "point" if abs(points) == 1 else "points"
    member = await ctx.guild.fetch_member(int(playerId))
    name = member.display_name
    message = f"{name} has earned {points} {pointWord}!" if points > 0 else f"{name} has lost {-points} {pointWord}."

    await ctx.send(message)


@bot.command(name='updateMemberTiers',
             usage="updateMemberTiers",
             aliases=["UpdateMemberTiers"],
             help="This updates the tiers for all players. Should primarily be used after updating the thresholds for tiers.")
async def updateRoles(ctx):
    db = cluster[str(ctx.guild.id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    data = list(player_data_collection.find({}))
    config_collection = db[CONFIG_COLLECTION]
    configFile = config_collection.find_one({})
    guild = ctx.guild
    tiers = configFile[TIERS_KEY]

    sortedTiers = []
    for key in tiers:
        sortedTiers.append([key, tiers[key]])

    def getPoints(lst):
        return lst[1]

    sortedTiers.sort(key=getPoints, reverse=False)

    roles = []
    for role_string, _ in sortedTiers:
        roles.append(discord.utils.get(guild.roles, name=role_string))

    for player in data:
        points = player["points"]
        member = await guild.fetch_member(player[ID_KEY])
        for role in roles:
            await member.remove_roles(role)
        for index in range(len(list(sortedTiers))):
            print(tiers[sortedTiers[index][0]])
            if tiers[sortedTiers[index][0]] > points:
                if index == 0:
                    print("0")
                    break
                await member.add_roles(roles[index - 1])
                break
        if index != 0:
            await member.add_roles(roles[-1])
    await ctx.send("Player roles have been updated")


def matchResultPoints(winner_id, loser_id, guild_id):
    tier_difference = 0
    point_difference = 0
    placement_difference = 0

    db = cluster[str(guild_id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    data = list(player_data_collection.find({}))
    print(data)

    winner_info = [entry for entry in data if entry[ID_KEY] == winner_id]
    if len(winner_info) == 0:
        winner_info = {
            ID_KEY: winner_id,
            "points": 0
        }
    else:
        winner_info = winner_info[0]

    loser_info = [entry for entry in data if entry[ID_KEY] == loser_id]
    if len(loser_info) == 0:
        loser_info = {
            ID_KEY: loser_id,
            "points": 0
        }
    else:
        loser_info = loser_info[0]

    isUpset = loser_info["points"] > winner_info["points"]
    maxPoints = loser_info["points"] if isUpset else winner_info["points"]
    minPoints = winner_info["points"] if isUpset else loser_info["points"]
    if minPoints != maxPoints:
        placement_difference = sum(map(lambda entry: minPoints < entry["points"] < maxPoints, data)) + 1
        placement_difference = -1 * placement_difference if isUpset else placement_difference

    config_collection = db[CONFIG_COLLECTION]
    configFile = config_collection.find_one({})

    if not TIERS_KEY in configFile.keys():
        tier_difference = 0
    else:
        tiers = configFile[TIERS_KEY]
        print(tiers)
        sortedTiers = []
        for key in tiers:
            sortedTiers.append([key, tiers[key]])

        def getPoints(lst):
            return lst[1]

        sortedTiers.sort(key=getPoints, reverse=False)
        winner_tier = -1
        loser_tier = -1

        for tier, points in sortedTiers:
            print(tier, points)
            if winner_info["points"] >= points:
                winner_tier += 1
            else:
                break

        for tier, points in sortedTiers:
            if loser_info["points"] >= points:
                loser_tier += 1
            else:
                break

        tier_difference = winner_tier - loser_tier
    point_difference = winner_info["points"] - loser_info["points"]
    winner_points_earned = parseFormmula.evaluateFormula(configFile[POINTS_GAINED_FORMULA_KEY], tier_difference,
                                                         point_difference, placement_difference)
    winner_points_earned = max(winner_points_earned, configFile[MIN_POINTS_GAINED_KEY])
    winner_points_earned = min(winner_points_earned, configFile[MAX_POINTS_GAINED_KEY])
    winner_points_earned = round(winner_points_earned, 4)

    loser_points_lost = parseFormmula.evaluateFormula(configFile[POINTS_LOST_FORMULA_KEY], tier_difference,
                                                      point_difference, placement_difference)
    loser_points_lost = max(loser_points_lost, configFile[MIN_POINTS_LOST_KEY])
    loser_points_lost = min(loser_points_lost, configFile[MAX_POINTS_LOST_KEY])
    loser_points_lost = round(loser_points_lost, 4)

    winner_info["points"] += winner_points_earned
    loser_info["points"] -= loser_points_lost

    player_data_collection.find_one_and_replace({ID_KEY: winner_id}, winner_info, upsert=True)
    player_data_collection.find_one_and_replace({ID_KEY: loser_id}, loser_info, upsert=True)

    new_winner_tier = -1
    new_loser_tier = -1

    for tier, points in sortedTiers:
        print(tier, points)
        if winner_info["points"] >= points:
            new_winner_tier += 1
        else:
            break

    for tier, points in sortedTiers:
        if loser_info["points"] >= points:
            new_loser_tier += 1
        else:
            break

    change_winner_tier = {}
    change_loser_tier = {}

    if winner_tier != new_winner_tier:
        change_winner_tier['add'] = sortedTiers[new_winner_tier][0] if new_winner_tier >= 0 else False
        change_winner_tier['remove'] = sortedTiers[winner_tier][0] if winner_tier >= 0 else False

    if loser_tier != new_loser_tier:
        change_loser_tier['add'] = sortedTiers[new_loser_tier][0] if new_loser_tier >= 0 else False
        change_loser_tier['remove'] = sortedTiers[loser_tier][0] if loser_tier >= 0 else False

    return winner_points_earned, loser_points_lost, change_winner_tier, change_loser_tier


@bot.event
async def on_raw_reaction_add(payload):
    db = cluster[str(payload.guild_id)]
    collection = db[PENDING_RESULTS_COLLECTION]
    messageInfo = collection.find_one({ID_KEY: payload.message_id})
    if messageInfo and str(messageInfo[ID_KEY]) == str(payload.message_id):
        if str(messageInfo["winner_id"]) == str(payload.user_id):
            messageInfo["winner_confirmed"] = True
        elif str(messageInfo["loser_id"]) == str(payload.user_id):
            messageInfo["loser_confirmed"] = True
        if messageInfo["winner_confirmed"] and messageInfo["loser_confirmed"]:
            channel = bot.get_channel(payload.channel_id)
            assert channel
            guild = bot.get_guild(payload.guild_id)
            winner = await guild.fetch_member(int(messageInfo["winner_id"]))
            loser = await guild.fetch_member(int(messageInfo["loser_id"]))
            winner_name = winner.name
            loser_name = loser.name
            winner_points, loser_points, change_winner_tier, change_loser_tier = matchResultPoints(
                messageInfo["winner_id"], messageInfo["loser_id"],
                payload.guild_id)
            if change_winner_tier:
                if change_winner_tier["add"]:
                    print(change_winner_tier["add"])
                    new_winner_role = discord.utils.get(guild.roles, name=change_winner_tier["add"])
                    await winner.add_roles(new_winner_role)
                if change_winner_tier["remove"]:
                    print(change_winner_tier["remove"])
                    old_winner_role = discord.utils.get(guild.roles, name=change_winner_tier["remove"])
                    await winner.remove_roles(old_winner_role)
            if change_loser_tier:
                if change_loser_tier["add"]:
                    print(change_loser_tier["add"])
                    new_loser_role = discord.utils.get(guild.roles, name=change_loser_tier["add"])
                    await loser.add_roles(new_loser_role)
                if change_loser_tier["remove"]:
                    print(change_loser_tier["remove"])
                    old_loser_role = discord.utils.get(guild.roles, name=change_loser_tier["remove"])
                    await loser.remove_roles(old_loser_role)
            collection.delete_one({ID_KEY: payload.message_id})
            confirmMessage = f"The result has been confirmed! {winner_name} has earned {winner_points} points while {loser_name} has lost {loser_points} points."
            await channel.send(confirmMessage)


@bot.event
async def on_guild_join(guild):
    db = cluster[str(guild.id)]
    collection = db[CONFIG_COLLECTION]
    collection.find_one_and_replace({}, INITIAL_CONFIG_FILE, upsert=True)


# TODO: Get some more error testing in, but this can likely be done after ppl use it and see how it goes
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        message = f"Be sure you use all required arguments! \nThe correct usage is: `{ctx.bot.command_prefix}" \
                  f"{ctx.command.usage}` "
        await ctx.send(message)


bot.run(TOKEN)
