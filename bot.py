import os

from pymongo import MongoClient

import discord
from discord.ext import commands
from dotenv import load_dotenv
from util import *

import parseFormmula

load_dotenv()
cluster = MongoClient(os.getenv('MONGO_DB_URL'))

TOKEN = os.getenv('DISCORD_TOKEN')


def get_command_prefix(_, message):
    db = cluster[str(message.guild.id)]
    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    command_prefix = configFile[COMMAND_PREFIX_KEY]
    return command_prefix


intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix=get_command_prefix, intents=intents)


def getPoints(lst):
    return lst[1]


def getSortedTiers(guild_id):
    sortedTiers = []

    db = cluster[str(guild_id)]
    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})

    if not TIERS_KEY in configFile.keys():
        return sortedTiers

    tiers = configFile[TIERS_KEY]
    for key in tiers:
        sortedTiers.append([key, tiers[key]])
    sortedTiers.sort(key=getPoints, reverse=False)
    return list(sortedTiers)


def getCurrentTier(member_points, guild_id):
    sortedTiers = getSortedTiers(guild_id)
    member_tier_index = NO_TIER_ROLE_INDEX
    for tier, points in sortedTiers:
        if member_points >= points:
            member_tier_index += 1
        else:
            break
    tier = '' if member_tier_index == NO_TIER_ROLE_INDEX else sortedTiers[member_tier_index]
    return tier, member_tier_index


async def adjustMemberTierRole(member_id, guild_id):
    db = cluster[str(guild_id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    member_data = player_data_collection.find_one({ID_KEY: member_id})
    guild = bot.get_guild(guild_id)
    sortedTiers = getSortedTiers(guild_id)

    member = await guild.fetch_member(member_id)
    points = member_data[POINTS_KEY]
    correct_role_string, _ = getCurrentTier(points, guild_id)

    if correct_role_string:
        correct_role_string = correct_role_string[0]

    for role in member.roles:
        if correct_role_string == role.name:
            return

    for role_string, _ in sortedTiers:
        if role_string != correct_role_string:
            await member.remove_roles(discord.utils.get(guild.roles, name=role_string))
    if correct_role_string:
        await member.add_roles(discord.utils.get(guild.roles, name=correct_role_string))


async def try_fetch_member(member_id, guild):
    try:
        user = await guild.fetch_member(member_id)
        return user
    except discord.HTTPException as e:
        print("Error retrieving members")
        print(e)
        return None
    except discord.Forbidden as e:
        print("Error retrieving members")
        print(e)
        return None


@bot.event
async def on_ready():
    for guild in bot.guilds:
        print(guild.name)
        async for member in guild.fetch_members():
            print(member.name + " " + str(member.id))


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
        message += "\nMinimum Points " + str(minPoints)

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
        message += "\nMinimum Points " + str(minPoints)

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

    tiers = {}
    if TIERS_KEY in configFile.keys():
        tiers = configFile[TIERS_KEY]

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
    matchingIndices = [index for index in indices if keys[index] == roleName]
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
    sortedTiers = getSortedTiers(ctx.guild.id)
    if len(sortedTiers) == 0:
        ctx.send("There are currently no tiers!")
        return

    message = "```TIER LISTING\n"

    for tier in sortedTiers:
        message += "\n" + tier[0] + ": " + str(tier[1])

    message += "```"
    await ctx.send(message)


@bot.command(name='leaderboard',
             help="Displays the ranked leaderboard for this server.",
             aliases=["Leaderboard", "LeaderBoard", "leaderBoard"])
async def displayLeaderboard(ctx):
    leaderboard = []

    db = cluster[str(ctx.guild.id)]
    collection = db[PLAYER_DATA_COLLECTION]
    data = list(collection.find({}))

    if not data:
        await ctx.send("There are current no players on the leaderboard!")

    for entry in data:
        user = await try_fetch_member(int(entry[ID_KEY]), ctx.guild)
        if user is not None:
            leaderboard.append([user.display_name, entry[POINTS_KEY]])

    message = "```"
    rank = 0
    leaderboard.sort(key=getPoints, reverse=True)

    for person in leaderboard:
        rank += 1
        message += "\n" + str(rank) + ". " + person[0] + " (" + str(person[1]) + ")"

    message += "```"
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
        WINNER_ID_KEY: winner_id,
        LOSER_ID_KEY: loser_id,
        WINNER_CONFIRMED_KEY: ctx.author.id == int(winner_id),
        LOSER_CONFIRMED_KEY: ctx.author.id == int(loser_id)
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
    config_collection = db[CONFIG_COLLECTION]

    pointWord = "point" if abs(points) == 1 else "points"
    member = await ctx.guild.fetch_member(int(playerId))
    name = member.display_name
    message = f"{name} has earned {points} {pointWord}!" if points > 0 else f"{name} has lost {-points} {pointWord}."

    await adjustMemberTierRole(playerId, ctx.guild.id)
    await ctx.send(message)





@bot.command(name='updateMemberTiers',
             usage="updateMemberTiers",
             aliases=["UpdateMemberTiers"],
             help="This updates the tiers for all players. Should primarily be used after updating the thresholds for tiers.")
async def updateRoles(ctx):
    db = cluster[str(ctx.guild.id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    data = list(player_data_collection.find({}))
    guild = ctx.guild

    sortedTiers = getSortedTiers(guild.id)

    roles = []
    for role_string, _ in sortedTiers:
        roles.append(discord.utils.get(guild.roles, name=role_string))

    if len(roles) == 0:
        await ctx.send("There are no currently set tiers.")
        return

    for player in data:
        points = player[POINTS_KEY]
        member = await try_fetch_member(player[ID_KEY], guild)
        if not member:
            continue

        for role in roles:
            await member.remove_roles(role)
        _, tier_index = getCurrentTier(points, guild.id)

        if tier_index == NO_TIER_ROLE_INDEX:
            continue
        await member.add_roles(roles[tier_index])

    await ctx.send("Player roles have been updated")


async def matchResultPoints(winner_id, loser_id, guild_id):
    placement_difference = 0

    db = cluster[str(guild_id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    data = list(player_data_collection.find({}))

    winner_info = [entry for entry in data if entry[ID_KEY] == winner_id]
    if len(winner_info) == 0:
        winner_info = {
            ID_KEY: winner_id,
            POINTS_KEY: 0
        }
    else:
        winner_info = winner_info[0]

    loser_info = [entry for entry in data if entry[ID_KEY] == loser_id]
    if len(loser_info) == 0:
        loser_info = {
            ID_KEY: loser_id,
            POINTS_KEY: 0
        }
    else:
        loser_info = loser_info[0]

    isUpset = loser_info[POINTS_KEY] > winner_info[POINTS_KEY]
    maxPoints = loser_info[POINTS_KEY] if isUpset else winner_info[POINTS_KEY]
    minPoints = winner_info[POINTS_KEY] if isUpset else loser_info[POINTS_KEY]
    points_for_members_in_server = []
    for entry in data:
        member = await try_fetch_member(entry[ID_KEY], bot.get_guild(guild_id))
        if member:
            points_for_members_in_server.append(entry[POINTS_KEY])
    if minPoints != maxPoints:
        placement_difference = sum(map(lambda points: minPoints < points < maxPoints, points_for_members_in_server)) + 1
        placement_difference = -1 * placement_difference if isUpset else placement_difference

    config_collection = db[CONFIG_COLLECTION]
    configFile = config_collection.find_one({})

    sortedTiers = getSortedTiers(guild_id)
    if len(sortedTiers) == 0:
        tier_difference = 0
    else:
        _, old_winner_tier_index = getCurrentTier(winner_info[POINTS_KEY], guild_id)
        _, old_loser_tier_index = getCurrentTier(loser_info[POINTS_KEY], guild_id)
        tier_difference = old_winner_tier_index - old_loser_tier_index

    point_difference = winner_info[POINTS_KEY] - loser_info[POINTS_KEY]
    winner_points_earned = parseFormmula.evaluateFormula(configFile[POINTS_GAINED_FORMULA_KEY], tier_difference,
                                                         point_difference, placement_difference)
    winner_points_earned = max(winner_points_earned, configFile[MIN_POINTS_GAINED_KEY])
    winner_points_earned = min(winner_points_earned, configFile[MAX_POINTS_GAINED_KEY])
    winner_points_earned = round(winner_points_earned, 3)

    loser_points_lost = parseFormmula.evaluateFormula(configFile[POINTS_LOST_FORMULA_KEY], tier_difference,
                                                      point_difference, placement_difference)
    loser_points_lost = max(loser_points_lost, configFile[MIN_POINTS_LOST_KEY])
    loser_points_lost = min(loser_points_lost, configFile[MAX_POINTS_LOST_KEY])
    loser_points_lost = round(loser_points_lost, 3)

    winner_info[POINTS_KEY] += winner_points_earned
    loser_info[POINTS_KEY] -= loser_points_lost

    player_data_collection.find_one_and_replace({ID_KEY: winner_id}, winner_info, upsert=True)
    player_data_collection.find_one_and_replace({ID_KEY: loser_id}, loser_info, upsert=True)

    return winner_points_earned, loser_points_lost


@bot.event
async def on_raw_reaction_add(payload):
    db = cluster[str(payload.guild_id)]
    collection = db[PENDING_RESULTS_COLLECTION]
    messageInfo = collection.find_one({ID_KEY: payload.message_id})
    if messageInfo and str(messageInfo[ID_KEY]) == str(payload.message_id):
        if str(messageInfo[WINNER_ID_KEY]) == str(payload.user_id):
            messageInfo[WINNER_CONFIRMED_KEY] = True
        elif str(messageInfo[LOSER_ID_KEY]) == str(payload.user_id):
            messageInfo[LOSER_CONFIRMED_KEY] = True
        if messageInfo[WINNER_CONFIRMED_KEY] and messageInfo[LOSER_CONFIRMED_KEY]:
            channel = bot.get_channel(payload.channel_id)
            assert channel

            guild = bot.get_guild(payload.guild_id)
            winner = await guild.fetch_member(int(messageInfo[WINNER_ID_KEY]))
            loser = await guild.fetch_member(int(messageInfo[LOSER_ID_KEY]))
            winner_name = winner.name
            loser_name = loser.name

            winner_points, loser_points = await matchResultPoints(
                messageInfo[WINNER_ID_KEY], messageInfo[LOSER_ID_KEY],
                payload.guild_id)

            await adjustMemberTierRole(messageInfo[WINNER_ID_KEY], payload.guild_id)
            await adjustMemberTierRole(messageInfo[LOSER_ID_KEY], payload.guild_id)
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
