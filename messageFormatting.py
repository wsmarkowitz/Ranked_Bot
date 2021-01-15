import discord

FOOTER_TEXT = "Fermata's Ranked Bot"


def formatResultsConfirmedMessage(winner_name, old_winner_points, new_winner_points, loser_name, old_loser_points, new_loser_points, icon_url):
    embed = discord.Embed(title="Match Results", color=discord.Color(0x961AFF),
                          description=f"The result has been confirmed. {winner_name} gains {new_winner_points - old_winner_points} points while {loser_name} loses {old_loser_points - new_loser_points} points."
                          )

    embed.set_thumbnail(url=icon_url)
    embed.set_footer(text=FOOTER_TEXT)

    embed.add_field(name=winner_name, value=f"`{old_winner_points} -> {new_winner_points}`", inline=True)
    embed.add_field(name=loser_name, value=f"`{old_loser_points} -> {new_loser_points}`", inline=True)
    return embed


def formatAdjustPointsMessage(name, old_points, new_points, icon_url):
    color = discord.Color(0x067203) if old_points < new_points else discord.Color(0xDB001B)
    points_change = new_points - old_points
    description = f"{name} has earned {points_change} points!" if points_change > 0 else f"{name} has lost {-points_change} points."
    embed = discord.Embed(title="Points Adjustment", color=color, description=description)

    embed.set_thumbnail(url=icon_url)
    embed.set_footer(text=FOOTER_TEXT)

    embed.add_field(name=name, value=f"`{old_points} -> {new_points}`", inline=True)
    return embed


def formatErrorMessage(message, icon_url):
    embed = discord.Embed(title="Error Message", color=discord.Color(0xDB001B), description=message)
    embed.set_thumbnail(url=icon_url)
    embed.set_footer(text=FOOTER_TEXT)
    return embed


def formatSuccessMessage(message, icon_url, title="Success Message"):
    embed = discord.Embed(title=title, color=discord.Color(0x067203), description=message)
    embed.set_thumbnail(url=icon_url)
    embed.set_footer(text=FOOTER_TEXT)
    return embed
