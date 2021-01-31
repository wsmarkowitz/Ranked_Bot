import os

from pymongo import MongoClient

from discord.ext import commands
from dotenv import load_dotenv
from util import *
from messageFormatting import *
from gamesForCharacterLists import *

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


def get_command_prefix_from_id(guild_id):
    db = cluster[str(guild_id)]
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


def tierIsValid(tier, guild_id):
    db = cluster[str(guild_id)]
    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    return tier in configFile[TIERS_KEY].keys()


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
            try:
                await member.remove_roles(discord.utils.get(guild.roles, name=role_string))
            except discord.Forbidden:
                raise PermissionError("The bot does not have permission to remove roles. Ensure that the bot permissions are higher than all roles associated with ranked tiers.")
                return
    if correct_role_string:
        try:
            await member.add_roles(discord.utils.get(guild.roles, name=correct_role_string))
        except discord.Forbidden:
            raise PermissionError(
                "The bot does not have permission to add roles. Ensure that the bot permissions are higher than all roles associated with ranked tiers.")


async def try_fetch_member(member_id, guild):
    user = guild.get_member(member_id)
    print(user)
    if user:
        print("gotten")
        return user
    try:
        user = await guild.fetch_member(member_id)
        print("fetched")
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
             usage="newCommandPrefix",
             aliases=["ChangeCommandPrefix", "changecommandprefix", "ChangeCommandprefix",
                      "changeCommandprefix", "ChangecommandPrefix, Changecommandprefix", "changecommandPrefix"])
async def changeCommandPrefix(ctx, command_prefix: str):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    collection = db[CONFIG_COLLECTION]
    collection.update_one({}, {"$set": {COMMAND_PREFIX_KEY: command_prefix}})
    embed = formatSuccessMessage(f"The command prefix has been set to `{command_prefix}`!", ctx.guild.icon_url)
    await ctx.send(embed=embed)


@bot.command(name="viewPointsFormulas",
              help="Lets you see what the formulas are for when someone wins or loses a match.",
              usage="")
async def viewPointsFormulas(ctx):
    db = cluster[str(ctx.guild.id)]
    collection = db[CONFIG_COLLECTION]
    config = collection.find_one({})
    pointsGainedFomula = config[POINTS_GAINED_FORMULA_KEY]
    pointsLostFomula = config[POINTS_LOST_FORMULA_KEY]
    minPointsGained = config[MIN_POINTS_GAINED_KEY]
    maxPointsGained = config[MAX_POINTS_GAINED_KEY]
    minPointsLost = config[MIN_POINTS_LOST_KEY]
    maxPointsLost = config[MAX_POINTS_LOST_KEY]
    message = f"```POINTS_GAINED: {pointsGainedFomula}"
    message += f"\nMIN_POINTS_GAINED: {minPointsGained}" if minPointsGained is not None else ""
    message += f"\nMAX_POINTS_GAINED: {maxPointsGained}" if maxPointsGained is not None else ""

    message += f"\nPOINTS_LOST: {pointsLostFomula}"
    message += f"\nMIN_POINTS_LOST: {minPointsLost}" if minPointsLost is not None else ""
    message += f"\nMAX_POINTS_LOST: {maxPointsLost}" if maxPointsLost is not None else ""
    message += "```"

    embed = formatSuccessMessage(message, ctx.guild.icon_url, title="View Formulas")
    await ctx.send(embed=embed)


@bot.command(name="pointsGained",
             help="Set the formula for when you gain points for a win. Any singular mathematical expression will "
                  "suffice. The supported symbols are '+', '-', '*', '/', '(', ')', 'TIER_DIFFERENCE' and "
                  "'POINT_DIFFERENCE'. Be sure to use a space between every symbol. "
                  "TIER_DIFFERENCE indicates how many tiers the winner is above the loser. POINT_DIFFERENCE indicates "
                  "how many more points the winner has over the loser. An example formula would be `5 + ( -1 * POINT_DIFFERENCE / 8 )`.",
             usage='"formula" minPointsGained (optional) maxPointsGained (optional)'
             )
async def changePointsGainedFomula(ctx, formula: str, minRange=None, maxRange=None):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    try:
        parseFormmula.evaluateFormula(formula, 0, 0)
    except SyntaxError as e:
        embed = formatErrorMessage(str(e), ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    if minRange and maxRange:
        if maxRange <= minRange:
            embed = formatErrorMessage("The minimum points value must be less than the maximum points value", ctx.guild.icon_url)
            await ctx.send(embed=embed)
            return

    minRange = int(minRange) if minRange and minRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
    maxRange = int(maxRange) if maxRange and maxRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None

    collection = db[CONFIG_COLLECTION]

    collection.update_one({}, {"$set": {POINTS_GAINED_FORMULA_KEY: formula}})
    message = f"The pointsGained info has been changed: ```Formula: {formula}"

    if minRange:
        collection.update_one({}, {"$set": {MIN_POINTS_GAINED_KEY: minRange}})
        message += "\nMinimum Points " + str(minRange)

    if maxRange:
        collection.update_one({}, {"$set": {MAX_POINTS_GAINED_KEY: maxRange}})
        message += "\nMaximum Points " + str(maxRange)

    message += "```"
    embed = formatSuccessMessage(message, ctx.guild.icon_url, title="Points Gained Formula")
    await ctx.send(embed=embed)


@bot.command(name="pointsLost",
             help="Set the formula for when you gain points for a win. Any singular mathematical expression will "
                  "suffice. The supported symbols are '+', '-', '*', '/', '(', ')', 'TIER_DIFFERENCE', and "
                  "'POINT_DIFFERENCE'. Be sure to use a space between every symbol. "
                  "TIER_DIFFERENCE indicates how many tiers the winner is above the loser. POINT_DIFFERENCE indicates "
                  "how many more points the winner has over the loser. An example formula would be `5 + ( -1 * POINT_DIFFERENCE / 8 )`. "
                  "\n \n This should be a positive number, as this number will be subtracted from the loser's point total.",
             usage='"formula" minPointsLost (optional) maxPointsLost (optional)'
             )
async def changePointsLostFomula(ctx, formula: str, minRange=None, maxRange=None):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    try:
        parseFormmula.evaluateFormula(formula, 0, 0)
    except SyntaxError as e:
        embed = formatErrorMessage(str(e), ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    minRange = int(minRange) if minRange and minRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None
    maxRange = int(maxRange) if maxRange and maxRange.replace('.', '', 1).replace('-', '', 1).isdigit() else None

    if minRange and maxRange:
        if maxRange <= minRange:
            embed = formatErrorMessage("The minimum points value must be less than the maximum points value", ctx.guild.icon_url)
            await ctx.send(embed=embed)
            return

    collection = db[CONFIG_COLLECTION]

    collection.update_one({}, {"$set": {POINTS_LOST_FORMULA_KEY: formula}})
    message = f"The pointsLost info has been changed: ```Formula: {formula}"

    if minRange:
        collection.update_one({}, {"$set": {MIN_POINTS_LOST_KEY: minRange}})
        message += "\nMinimum Points " + str(minRange)

    if maxRange:
        collection.update_one({}, {"$set": {MAX_POINTS_LOST_KEY: maxRange}})
        message += "\nMaximum Points " + str(maxRange)

    message += "```"
    embed = formatSuccessMessage(message, ctx.guild.icon_url, title="Points Lost Formula")
    await ctx.send(embed=embed)


@bot.command(name="setTier",
             usage="roleName points",
             help="Be sure the role name already is an existing role before using this command. "
                  "Also note that the number of points is the lower bound for reaching this tier/rank.",
             aliases=["settier", "SetTier", "Settier"])
async def setTier(ctx, roleName: str, points: int):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    if not [True for role in ctx.guild.roles if role.name == roleName]:
        embed = formatErrorMessage("That is not a valid role on this server! Remember that this is case sensitive!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})

    tiers = {}
    if TIERS_KEY in configFile.keys():
        tiers = configFile[TIERS_KEY]

    tiers[roleName] = points
    collection.update_one({}, {"$set": {TIERS_KEY: tiers}})
    embed = formatSuccessMessage(f"The tier *{roleName}* now requires at least *{points}* points.", ctx.guild.icon_url, "Set Tier")
    await ctx.send(embed=embed)


@bot.command(name="removeTier",
             usage="roleName",
             help="Be sure the role name already is currently set before removing",
             aliases=["removetier", "RemoveTier", "Removetier"])
async def removeTier(ctx, roleName: str):
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return


    collection = db[CONFIG_COLLECTION]
    configFile = collection.find_one({})
    if not configFile[TIERS_KEY]:
        embed = formatErrorMessage("That is not a tier already set! Remember that this is case sensitive!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return
    keys = list(configFile[TIERS_KEY].keys())
    indices = range(len(keys))
    matchingIndices = [index for index in indices if keys[index] == roleName]
    if len(matchingIndices) == 0:
        embed = formatErrorMessage("That is not a tier already set! Remember that this is case sensitive!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    matchingIndex = matchingIndices[0]
    del configFile[TIERS_KEY][keys[matchingIndex]]
    collection.update_one({}, {"$set": {TIERS_KEY: configFile[TIERS_KEY]}})
    embed = formatSuccessMessage(f"The tier *{roleName}* has been removed.", ctx.guild.icon_url, "Remove Tiers")
    await ctx.send(embed=embed)


@bot.command(name="viewTiers",
             usage="",
             help="Displays the tier names and their minimum point values.",
             aliases=["viewtiers", "ViewTiers", "Viewtiers"])
async def viewTiers(ctx):
    sortedTiers = list(reversed(getSortedTiers(ctx.guild.id)))
    if len(sortedTiers) == 0:
        embed = formatSuccessMessage("There are currently no tiers!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    message = "```"

    for tier in sortedTiers:
        message += "\n" + tier[0] + ": " + str(tier[1])

    message += "```"
    embed = formatSuccessMessage(message, ctx.guild.icon_url, title="Tiers List")
    await ctx.send(embed=embed)


@bot.command(name='leaderboard',
             help="Displays the ranked leaderboard for this server. You may also add an argument that is a tier if you would like to see te rankings for only that tier.",
             usage="tier (optional)",
             aliases=["Leaderboard", "LeaderBoard", "leaderBoard"])
async def displayLeaderboard(ctx, tier=None):
    leaderboard = []
    db = cluster[str(ctx.guild.id)]
    collection = db[PLAYER_DATA_COLLECTION]
    data = list(collection.find({}))

    if not data:
        embed = formatSuccessMessage("There are currently no players on the leaderboard!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    if tier and not tierIsValid(tier, ctx.guild.id):
        embed = formatErrorMessage("There is no such tier currently set! Remember that this is case-sensitive.", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    for entry in data:
        user = await try_fetch_member(int(entry[ID_KEY]), ctx.guild)
        if user is not None:
            for role in user.roles:
                if not tier or tier == role.name:
                    leaderboard.append([user.display_name, entry[POINTS_KEY]])
                    break

    message = "```"
    rank = 0
    leaderboard.sort(key=getPoints, reverse=True)

    if len(leaderboard) == 0:
        embed = formatSuccessMessage("There are currently no players in this tier!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    for person in leaderboard:
        rank += 1
        message += "\n" + str(rank) + ". " + person[0] + " (" + str(person[1]) + ")"

    message += "```"
    title = f"{tier if tier else 'Full'} Leaderboard"
    embed = formatSuccessMessage(message, ctx.guild.icon_url, title=title)
    await ctx.send(embed=embed)


@bot.command(name='report',
             usage="@winner, @loser",
             help="Report the reuslts of a set with this. Be sure to tag the winner first and the loser second. "
                  "Afterward, the bot will post a message for the players to confirm, at which point, "
                  "the resulting points will be adjusted.",
             aliases=["Report, results, Results, reportSet, ReportSet, reportset, Reportset"])
async def reportResult(ctx, winnerMention: str, loserMention: str):
    winner_id = str(getIDFromMention(winnerMention))
    loser_id = str(getIDFromMention(loserMention))
    guild = ctx.guild

    if not (winner_id.isnumeric() or loser_id.isnumeric()):
        embed = formatErrorMessage("User not found. Be sure that you're correctly tagging the players.\n\nIf this issue persists, there is likely an issue with the bot's permissions or with Discord.", guild.icon_url)
        await ctx.send(embed=embed)
        return

    winnerTag = await try_fetch_member(int(winner_id), guild)
    loserTag = await try_fetch_member(int(loser_id), guild)

    if not (winnerTag and loserTag):
        embed = formatErrorMessage("User not found. Be sure that you're correctly tagging the players.\n\nIf this issue persists, there is likely an issue with the bot's permissions or with Discord.", guild.icon_url)
        await ctx.send(embed=embed)
        return

    embed = formatSuccessMessage(f"{winnerMention} has beaten {loserMention}. React to this message if that is correct.", guild.icon_url)

    sent_message = await ctx.send(embed=embed)
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
             usage="<@Member> <PointChange>",
             aliases=["Adjust", "adjustPoints", "AdjustPoints", "adjustpoints"])
async def adjustPoints(ctx, mention: str, points: int):
    playerId = getIDFromMention(mention)
    db = cluster[str(ctx.guild.id)]
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not a score reporter for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    collection = db[PLAYER_DATA_COLLECTION]
    player_info = collection.find_one({ID_KEY: playerId})
    print(player_info)
    if not player_info:
        player_info = {
            ID_KEY: playerId,
            POINTS_KEY: 0
        }
    print("success")
    old_points = player_info[POINTS_KEY]
    new_points = old_points + points
    collection.find_one_and_update({ID_KEY: playerId}, {"$inc": {POINTS_KEY: points}}, upsert=True)

    member = await ctx.guild.fetch_member(int(playerId))
    name = member.display_name

    try:
        await adjustMemberTierRole(playerId, ctx.guild.id)
    except PermissionError as e:
        embed = formatErrorMessage(str(e), ctx.guild.icon_url)
        await ctx.send(embed=embed)

    embed = formatAdjustPointsMessage(name, old_points, new_points, ctx.guild.icon_url)
    await ctx.send(embed=embed)


@bot.command(name='updateMemberTiers',
             usage="",
             aliases=["UpdateMemberTiers"],
             help="This updates the tiers for all players. Should primarily be used after updating the thresholds for tiers.")
async def updateRoles(ctx):
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    db = cluster[str(ctx.guild.id)]
    player_data_collection = db[PLAYER_DATA_COLLECTION]
    data = list(player_data_collection.find({}))
    guild = ctx.guild

    sortedTiers = getSortedTiers(guild.id)

    roles = []
    for role_string, _ in sortedTiers:
        roles.append(discord.utils.get(guild.roles, name=role_string))

    if len(roles) == 0:
        embed = formatSuccessMessage("There are no currently set tiers.", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    for player in data:
        points = player[POINTS_KEY]
        member = await try_fetch_member(player[ID_KEY], guild)
        if not member:
            continue

        for role in roles:
            try:
                await member.remove_roles(role)
            except discord.Forbidden:
                embed = formatErrorMessage("The bot does not have permission to remove roles. Ensure that the bot permissions are higher than all roles associated with ranked tiers.", ctx.guild.icon_url)
                ctx.send(embed=embed)
                return
        _, tier_index = getCurrentTier(points, guild.id)

        if tier_index == NO_TIER_ROLE_INDEX:
            continue
        await member.add_roles(roles[tier_index])

    embed = formatSuccessMessage("Player roles have been updated", ctx.guild.icon_url)
    await ctx.send(embed=embed)
    return


@bot.command(name="addCharacterRoles",
             usage=f"game\n"
                   f"The currently supported games are {gamesSupported}",
             aliases=["AddCharacterRoles"],
             help="This adds the character roles for a given game. For your convenience, it is imperative that you do not change the names of these roles and that you ensure that the role for this bot is above these roles.")
async def addCharacterRoles(ctx, game: str):
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    if game not in gamesSupported:
        embed = formatErrorMessage(f"This is not a supported game! The currently supported games are: {gamesSupported}", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    characterList = gameToCharacterList[game]
    guild = ctx.guild
    for character in characterList:
        print(character)
        # await guild.create_role(name=character)
        role = discord.utils.get(guild.roles, name=character)
        if role is not None:
            continue
        try:
            await guild.create_role(name=character)
        except discord.Forbidden:
            await ctx.send('This bot does not have permission to Manage Roles. Please change this before trying again.')
            return

    embed = formatSuccessMessage("The character roles have been added!", ctx.guild.icon_url)
    await ctx.send(embed=embed)


@bot.command(name="deleteCharacterRoles",
             usage=f"game\n"
                   f"The currently supported games are {gamesSupported}",
             aliases=["DeleteCharacterRoles"],
             help="This deletes the character roles for a given game.")
async def deleteCharacterRoles(ctx, game: str):
    if not userHasAdminRole(ctx.message.author):
        embed = formatErrorMessage("You are not an admin for the ranked bot!", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    if game not in gamesSupported:
        embed = formatErrorMessage(f"This is not a supported game! The currently supported games are: {gamesSupported}", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    characterList = gameToCharacterList[game]
    guild = ctx.guild
    for character in characterList:
        role = discord.utils.get(guild.roles, name=character)
        if role is None:
            continue
        try:
            await role.delete()
        except discord.Forbidden:
            await ctx.send('This bot does not have permission to Manage Roles. Please change this before trying again.')
            return

    embed = formatSuccessMessage("The character roles have been removed!", ctx.guild.icon_url)
    await ctx.send(embed=embed)


@bot.command(name="character",
             usage=f"game character\n"
                   f"The currently supported games are {gamesSupported}",
             aliases=["Character"],
             help="This toggles whether or not the author has the listed role. The role will be added if they do not already have it. If they already have the role, it will be removed.")
async def toggleCharacterRoleForPlayer(ctx, game: str, characterAlias: str):
    if game not in gamesSupported:
        embed = formatErrorMessage(f"This is not a supported game! The currently supported games are: {gamesSupported}", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    characterList = gameToCharacterList[game]
    character = gameToCharacterAliases[game][characterAlias.lower()]
    if character in characterList:
        guild = ctx.guild
        role = discord.utils.get(guild.roles, name=character)
        member = ctx.message.author
        for member_role in member.roles:
            print(member_role)
            if character == member_role.name:
                try:
                    await member.remove_roles(role)
                    embed = formatSuccessMessage(f"You no longer have the {character} role!", ctx.guild.icon_url)
                    await ctx.send(embed=embed)
                    return
                except discord.Forbidden:
                    embed = formatErrorMessage(
                        "The bot does not have permission to remove roles. Ensure that the bot permissions are higher than all roles associated with ranked tiers.",
                        ctx.guild.icon_url)
                    ctx.send(embed=embed)
                    return

        try:
            await member.add_roles(role)
        except discord.Forbidden:
            embed = formatErrorMessage(
                "The bot does not have permission to add roles. Ensure that the bot permissions are higher than all roles associated with ranked tiers.",
                ctx.guild.icon_url)
            ctx.send(embed=embed)
            return

    embed = formatSuccessMessage(f"You now have the {character} role!", ctx.guild.icon_url)
    await ctx.send(embed=embed)


@bot.command(name="viewCharacterRoles",
             usage=f"game\n"
                   f"The currently supported games are {gamesSupported}",
             aliases=["ViewCharacterRoles"],
             help="This displays the characters for a given game.")
async def viewCharacterRoles(ctx, game: str):
    if game not in gamesSupported:
        embed = formatErrorMessage(f"This is not a supported game! The currently supported games are: {gamesSupported}", ctx.guild.icon_url)
        await ctx.send(embed=embed)
        return

    characterList = gameToCharacterList[game]
    characterListString = "\n".join(characterList)
    message = f"Character List for {game}:\n\n{characterListString}"

    embed = formatSuccessMessage(message, ctx.guild.icon_url)
    await ctx.send(embed=embed)


async def matchResultPoints(winner_id, loser_id, guild_id):
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

    points_for_members_in_server = []
    for entry in data:
        member = await try_fetch_member(entry[ID_KEY], bot.get_guild(guild_id))
        if member:
            points_for_members_in_server.append(entry[POINTS_KEY])

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
                                                         point_difference)
    winner_points_earned = max(winner_points_earned, configFile[MIN_POINTS_GAINED_KEY])
    winner_points_earned = min(winner_points_earned, configFile[MAX_POINTS_GAINED_KEY])

    loser_points_lost = parseFormmula.evaluateFormula(configFile[POINTS_LOST_FORMULA_KEY], tier_difference,
                                                      point_difference)
    loser_points_lost = max(loser_points_lost, configFile[MIN_POINTS_LOST_KEY])
    loser_points_lost = min(loser_points_lost, configFile[MAX_POINTS_LOST_KEY])

    old_winner_points = winner_info[POINTS_KEY]
    old_loser_points = loser_info[POINTS_KEY]

    winner_info[POINTS_KEY] += winner_points_earned
    loser_info[POINTS_KEY] -= loser_points_lost

    new_winner_points = winner_info[POINTS_KEY]
    new_loser_points = loser_info[POINTS_KEY]

    player_data_collection.find_one_and_replace({ID_KEY: winner_id}, winner_info, upsert=True)
    player_data_collection.find_one_and_replace({ID_KEY: loser_id}, loser_info, upsert=True)

    return old_winner_points, new_winner_points, old_loser_points, new_loser_points


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

            old_winner_points, new_winner_points, old_loser_points, new_loser_points = await matchResultPoints(
                messageInfo[WINNER_ID_KEY], messageInfo[LOSER_ID_KEY],
                payload.guild_id)
            try:
                await adjustMemberTierRole(messageInfo[WINNER_ID_KEY], payload.guild_id)
                await adjustMemberTierRole(messageInfo[LOSER_ID_KEY], payload.guild_id)
            except PermissionError as e:
                embed = formatErrorMessage(str(e), guild.icon_url)
                await channel.send(embed=embed)

            collection.delete_one({ID_KEY: payload.message_id})
            embed = formatResultsConfirmedMessage(winner_name, old_winner_points, new_winner_points, loser_name, old_loser_points, new_loser_points, guild.icon_url)
            await channel.send(embed=embed)


@bot.event
async def on_guild_join(guild):
    db = cluster[str(guild.id)]
    collection = db[CONFIG_COLLECTION]
    collection.find_one_and_replace({}, INITIAL_CONFIG_FILE, upsert=True)


# TODO: Get some more error testing in, but this can likely be done after ppl use it and see how it goes
@bot.event
async def on_command_error(ctx, error):
    command_prefix = get_command_prefix_from_id(ctx.guild.id)
    if isinstance(error, commands.errors.MissingRequiredArgument):
        error_message = f"Be sure you use all required arguments! \nThe correct usage is: `{command_prefix}" \
                  f"{ctx.command.usage}` "
    elif isinstance(error, commands.errors.BadArgument):
        error_message = f"Doublecheck all the required arguments! Remember that all points values must be integers. \nThe correct usage is: `{command_prefix}" \
                  f"{ctx.command.usage}` "
    elif isinstance(error, commands.errors.CommandNotFound):
        error_message = f"This isn't a command! Be sure to use {command_prefix}help if you're unsure about what commands we have available!"
    elif isinstance(error, commands.errors.CommandInvokeError):
        error_message = f"An error has occurred while running the command. \n" \
                        f"```{error}```\n" \
                        f"If this issue persists, this may be a bug. Let Fermata#0765 know so that we can resolve the issue ASAP."
    elif isinstance(error, commands.errors.ExpectedClosingQuoteError):
        error_message = "An error has occurred. Not all quotation marks are closed."
    elif isinstance(error, commands.errors.InvalidEndOfQuotedStringError):
        error_message = "An error has occurred. Be sure to include a space after every ending quote."
    else:
        error_message = f"An unknown error has occurred. Please message Fermata#0765 with the following error if you'd like to submit a report.```\n{type(error)}\n{error}```"

    embed = formatErrorMessage(error_message, ctx.guild.icon_url)
    await ctx.send(embed=embed)


bot.run(TOKEN)
