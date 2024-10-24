import asyncio
from contextlib import suppress
from typing import Literal, Optional

import aiohttp
import disnake
from disnake.ext import commands, tasks

import config
import ws
import datatypes
from modules import cmdlogger
from modules import misc
from modules import mojang
from modules import usermanager
from modules import verifier
from modules import tradereport


TSKS = []

bot = commands.InteractionBot(
    intents=disnake.Intents(
        automod=False,
        automod_configuration=False,
        automod_execution=False,
        bans=False,
        dm_messages=False,
        dm_reactions=False,
        dm_typing=False,
        emojis=False,
        emojis_and_stickers=False,
        guild_messages=True,
        guild_reactions=False,
        guild_scheduled_events=False,
        guild_typing=False,
        guilds=True,
        integrations=False,
        invites=False,
        members=True,
        message_content=True,
        moderation=True,
        presences=False,
        voice_states=False,
        webhooks=False
    )
)


# noinspection PyAsyncCall
@bot.event
async def on_ready():
    asyncio.create_task(ws.start())
    asyncio.create_task(bot.change_presence(
        activity=disnake.Activity(
            type=disnake.ActivityType.watching,
            name="Collector's Hub"
        )
    ))
    for TSK in TSKS:
        if not TSK.is_running():
            TSK.start()
    verification_channel = bot.get_channel(config.VERIFICATION_CHANNEL)
    async for msg in verification_channel.history(limit=None):
        if msg.author.id != config.BOT_DEVELOPER_ID:
            asyncio.create_task(msg.delete())
    print('bot ready')


@bot.event
async def on_member_ban(guild: disnake.Guild, user: disnake.User):
    if guild.id != config.GUILD_ID:
        return
    ban = await guild.fetch_ban(user)
    await usermanager.log_ban(user.id, reason=ban.reason if ban else None)

    if not ban.reason:
        # im SURE there's a nicer looking way to do this, but according to the disnake support
        # server, the only way to get the moderator responsible is through audit logs
        moderator: Optional[disnake.Member] = None
        async for audit_ban in guild.audit_logs(limit=5, action=disnake.AuditLogAction.ban):
            if audit_ban.target.id == user.id:
                # IDEs don't like this since AuditLogEntry.user isn't always Member, but in this instance it is:
                moderator = audit_ban.user
                break
        channel = bot.get_channel(config.STAFF_CHANNEL)
        await channel.send(f"{(moderator.mention + ' ') if moderator else ''}"
                           f"**{disnake.utils.escape_markdown(ban.user.name)}** ({ban.user.mention}) "
                           f"was banned without reason. Please remember to provide a reason when banning users!!!!")


@bot.event
async def on_message(message: disnake.Message):
    if message.content.startswith('>exec') and await bot.is_owner(message.author):
        try:
            tmp_dic = {}
            executing_string = "async def temp_func():\n    {}\n".format(message.content.partition("\n")[2].strip("`")
                                                                         .replace("\n", "    \n    ")
                                                                         .replace('”', '"')
                                                                         .replace("’", "'")
                                                                         .replace("‘", "'"))
            print(executing_string)
            exec(executing_string, {**globals(), **locals()}, tmp_dic)
            await tmp_dic['temp_func']()
        except Exception as e:
            print(f"Error while running exec code:\n{e}")
            await message.reply(f"Error while running code:\n```{e}```")
    if message.channel.id == config.VERIFICATION_CHANNEL and not await bot.is_owner(message.author):
        await asyncio.sleep(60)
        with suppress(disnake.errors.NotFound):
            await message.delete()


@bot.event
async def on_button_click(inter: disnake.MessageInteraction):
    button_type, button_data = inter.component.custom_id.split('|', 1)
    match button_type:
        case tradereport.BUTTON_ID:
            return await tradereport.on_button_click(inter, button_data)
    await inter.send(embed=misc.make_error(
        "Invalid Button",
        f"Unknown button type: `{disnake.utils.escape_markdown(button_type)}`"
    ))


@bot.slash_command(
    name="verify",
    description="Link your Discord account to your Hypixel account"
)
async def verify_command(inter: disnake.AppCmdInter,
                       ign: str = misc.ign_param('Your IGN')):
    await inter.response.defer()
    if not inter.guild or (inter.guild and inter.guild.id != config.GUILD_ID):
        return await inter.send(embed=misc.NOT_GUILD_ERROR)
    await verifier.verify_command(inter, ign)


@bot.slash_command(
    name="unverify",
    description="Unlink your Discord account from your Hypixel account"
)
async def unverify_command(inter: disnake.AppCmdInter):
    await inter.response.defer()
    if not inter.guild or (inter.guild and inter.guild.id != config.GUILD_ID):
        return await inter.send(embed=misc.NOT_GUILD_ERROR)
    await verifier.unverify_command(inter)


@bot.slash_command(
    name="update",
    description="Updates your item roles"
)
async def update_command(inter: disnake.AppCmdInter):
    await inter.response.defer()
    if not inter.guild or (inter.guild and inter.guild.id != config.GUILD_ID):
        return await inter.send(embed=misc.NOT_GUILD_ERROR)
    await verifier.update_command(inter)


@bot.slash_command(
    name="info",
    description="Get information about the bot"
)
async def info_command(inter: disnake.AppCmdInter):
    await inter.response.defer()
    await inter.send(f"""This bot was made by {config.BOT_DEVELOPER_MENTION} for the Collector's Hub Discord server.
    
The bot was made to give out item roles automatically, but is now much more.

The bot is open source: <https://github.com/RagingEnby/CHUB-Bot>

If you have any other questions, feel free to reach out to {config.BOT_DEVELOPER_MENTION}.""")


@bot.slash_command(
    name="report-trade",
    description="Report a trade for it to be sent in <#1201283974924861470>"
)
async def report_trade_command(
    inter: disnake.AppCmdInter,
    seller: str = misc.ign_param('The player who sold the item'),
    buyer: str = misc.ign_param('The player who bought the item'),
    date: str = commands.param(description="PLEASE USE DD/MM/YYYY FORMAT"),
    item: str = commands.param(),
    price: str = commands.param(),
    image: disnake.Attachment = commands.param(description="An image of the trade"),
    notes: Optional[str] = commands.param(default=None, description="Any notes you want to add")
):
    await tradereport.report_trade_command(inter, seller, buyer, date, item, price, image, notes)
    


@bot.slash_command(
    name="moderation",
    description="Various commands to help server moderators."
)
async def moderation(_: disnake.AppCmdInter):
    return


@moderation.sub_command(
    name="give-role",
    description="Give a role to a user"
)
async def moderation_give_role_command(inter: disnake.AppCmdInter, member: disnake.Member, role: disnake.Role):
    if not await misc.validate_mod_cmd(inter, role):
        return
    if role.id == config.STAFF_ROLE:
        return await inter.send(embed=misc.make_error(
            "cannot give this role",
            f"The bot is manually set to not give out the <@{config.STAFF_ROLE}> role."
        ))
    try:
        await member.add_roles(role)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "no permissions",
            f"I do not have permissions to give out the {role.mention} role."
        ))
    await inter.send(embed=misc.make_success(
        "success",
        f"Granted {member.mention} the {role.mention} role!"
    ))


@moderation.sub_command(
    name="remove-role",
    description="Remove a role from a user"
)
async def moderation_remove_role_command(inter: disnake.AppCmdInter, member: disnake.Member, role: disnake.Role):
    if not await misc.validate_mod_cmd(inter, role):
        return
    try:
        await member.remove_roles(role)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "no permissions",
            f"I do not have permissions to remove the {role.mention} role."
        ))
    await inter.send(embed=misc.make_success(
        "success",
        f"Removed the {role.mention} role from {member.mention}."
    ))


@moderation.sub_command(
    name="ban",
    description="Ban a user from the server"
)
async def moderation_ban_command(inter: disnake.AppCmdInter, member: disnake.Member, reason: str):
    if not await misc.validate_mod_cmd(inter, member.top_role):
        return
    if not reason.replace(' ', ''):
        return await inter.send(embed=misc.make_error(
            "no ban reason",
            "You must provide a ban reason."
        ))

    reason = reason + f" | Banned by {inter.author.name} ({inter.author.id})"
    try:
        await member.send(f'You were banned from CHUB for reason `{disnake.utils.escape_markdown(reason)}`')
    except Exception as e:
        print("unable to dm member during ban:", member.name, member.id, e)
    try:
        await member.ban(reason=reason)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "no permissions",
            f"I do not have permissions to ban {member.mention}."
        ))
    await inter.send(embed=misc.make_success(
        "success",
        f"Banned {member.mention} for reason `{disnake.utils.escape_markdown(reason)}`."
    ))


# noinspection DuplicatedCode
@moderation.sub_command(
    name="unblacklist",
    description="Unblacklist a Minecraft player from the server"
)
async def moderation_unban_command(inter: disnake.AppCmdInter, player: str = commands.Param(
    autocomplete=usermanager.autocomplete_banned,
    description="The Minecraft UUID of the player to unblacklist",
    min_length=32,
    max_length=32
)):
    if not await misc.validate_mod_cmd(inter):
        return
    player = player.replace('-', '')
    player_obj = await mojang.get(player)

    if player_obj is None:
        return await inter.send(embed=misc.make_error(
            "invalid account",
            f"There is no account with the UUID `{disnake.utils.escape_markdown(player)}`!"
        ))

    if player_obj.uuid not in usermanager.BannedUsers:
        return await inter.send(embed=misc.make_error(
            "not banned",
            f"Account `{disnake.utils.escape_markdown(player)}` is not blacklisted."
        ))
    del usermanager.BannedUsers[player_obj.uuid]
    await usermanager.BannedUsers.save()
    await inter.send(embed=misc.make_success(
        "success",
        f"`{disnake.utils.escape_markdown(player)}` is no longer blacklisted!"
    ))


# noinspection DuplicatedCode
@moderation.sub_command(
    name="blacklist",
    description="Blacklist a Minecraft player from the server"
)
async def moderation_blacklist_command(inter: disnake.AppCmdInter, player: str = commands.Param(
    description="The Minecraft UUID of the player to blacklist",
    min_length=32,
    max_length=32
)):
    if not await misc.validate_mod_cmd(inter):
        return
    player = player.replace('-', '')
    player_obj = await mojang.get(player)

    if player_obj is None:
        return await inter.send(embed=misc.make_error(
            "invalid account",
            f"There is no account with the UUID `{disnake.utils.escape_markdown(player)}`!"
        ))

    if player_obj.uuid in usermanager.BannedUsers:
        return await inter.send(embed=misc.make_error(
            "already banned",
            f"Account `{disnake.utils.escape_markdown(player)}` is already blacklisted."
        ))
    usermanager.BannedUsers[player_obj.uuid] = f"{player_obj.uuid} | Banned by {inter.author.name} ({inter.author.id})"
    await usermanager.BannedUsers.save()


@moderation.sub_command(
    name="bulk-blacklist",
    description="Blacklist a group of players at once"
)
async def moderation_bulk_blacklist_command(inter: disnake.AppCmdInter, file: disnake.Attachment, reason: str):
    if not await misc.validate_mod_cmd(inter):
        return
    invalid_format_err = misc.make_error(
        "Invalid File",
        "Please ensure your file is a `.txt` file in this format:\n```RagingEnby\nTGWaffles\nFoe\nVinush```"
    )
    if not file.filename.endswith('.txt'):
        return await inter.send(embed=invalid_format_err)
    data = await file.read()
    igns = [line.strip() for line in data.decode().split('\n')]
    players = await mojang.bulk_get(igns)
    bans = 0
    for player in players:
        usermanager.BannedUsers[player.uuid] = f"{player.uuid} | {reason} | Bulk banned by {inter.author.name} ({inter.author.id})"
        member = inter.guild.get_member(usermanager.LinkedUsers[player.uuid]) if player.uuid in usermanager.LinkedUsers else None
        if member:
            print(f'banning {member.name} from from a bulk blacklist ({player.name} {player.uuid})')
            await member.ban(f"{reason} | Bulk banned by {inter.author.name} ({inter.author.id})")
            bans += 1
    await usermanager.BannedUsers.save()
    await inter.send(embed=misc.make_success(
        "Done!",
        f"Blacklisted `{len(players)}` from the server and banned `{bans}` server members"
    ))
    


@moderation.sub_command(
    name="force-verify",
    description="Runs /verify as a different user"
)
async def moderation_force_verify_command(inter: disnake.AppCmdInter, member: disnake.Member, ign: str):
    if not await misc.validate_mod_cmd(inter):
        return
    await verifier.verify_command(inter, ign, member)


@moderation.sub_command(
    name="force-update",
    description="Runs /update as a different user"
)
async def moderation_force_update_command(inter: disnake.AppCmdInter, member: disnake.Member):
    if not await misc.validate_mod_cmd(inter):
        return
    await verifier.update_command(inter, member)


@moderation.sub_command(
    name="force-unverify",
    description="Runs /unverify as a different user"
)
async def moderation_force_unverify_command(inter: disnake.AppCmdInter, member: disnake.Member):
    if not await misc.validate_mod_cmd(inter):
        return
    await verifier.unverify_command(inter, member)


@bot.slash_command(
    name="ec",
    description="Sends the link to Exotic Cafe Discord"
)
async def ec_command(inter: disnake.AppCmdInter):
    await inter.response.send_message("You can sell your Exotics here!\nhttps://discord.gg/QumkPh6vGd")


@bot.slash_command(
    name="cc",
    description="Sends the link to Crystal Cafe Discord"
)
async def cc_command(inter: disnake.AppCmdInter):
    await inter.response.send_message(
        "Sell your Crystal/Fairy armor here!\nhttps://discord.gg/crystal-cafe-873758934224232468")


@bot.slash_command(
    name="tem",
    description="Sends the link to Thomas's Community Discord (iTEM Discord)"
)
async def tem_command(inter: disnake.AppCmdInter):
    await inter.response.send_message("Download the iTEM mod here!\nhttps://discord.gg/item-932106421338779709")


@bot.event
async def on_slash_command(inter: disnake.AppCmdInter):
    await cmdlogger.on_slash_command(inter)


@bot.event
async def on_slash_command_completion(inter: disnake.AppCmdInter):
    await cmdlogger.on_slash_command_completion(inter)


async def update_players_task_single(uuid: str, member: disnake.Member,
                                     session: Optional[aiohttp.ClientSession] = None):
    player = await mojang.get(uuid, session=session)
    await verifier.update_member(member, player=player, session=session)


@tasks.loop(seconds=120)
async def update_linked_players_task():
    async with aiohttp.ClientSession() as session:
        member_dict = await misc.get_member_dict(bot)
        linked_users = await misc.randomize_dict_order(usermanager.LinkedUsers.data)
        for uuid, discord_id in linked_users.items():
            if discord_id not in member_dict or discord_id == bot.user.id:
                continue
            await update_players_task_single(uuid, member_dict[discord_id], session=session)
            await asyncio.sleep(6.5)  # rate limit sucks ass


TSKS.append(update_linked_players_task)


@tasks.loop(seconds=60)
async def ensure_all_verified_task():
    linked_user_ids = list(usermanager.LinkedUsers.values())
    for verified_role in [await misc.get_role(bot, role_id) for role_id in config.REQUIRES_VERIFICATION]:
        if verified_role is None:
            continue
        for member in verified_role.members:
            if member.id not in linked_user_ids:
                await verifier.remove_verification(member)


TSKS.append(ensure_all_verified_task)


@tasks.loop(seconds=30)
async def ensure_tasks_working():
    broken_tasks = [tsk for tsk in TSKS if not tsk.is_running()]
    if not broken_tasks:
        return
    channel = bot.get_channel(config.BOT_DEV_CHANNEL)
    formatted_tasks = '\n'.join([str(tsk) for tsk in broken_tasks])
    await channel.send(f"{config.BOT_DEVELOPER_MENTION} `{len(broken_tasks)}` tasks broke:\n```{formatted_tasks}```")
    for tsk in broken_tasks:
        tsk.start()


TSKS.append(ensure_tasks_working)

# @bot.event
# async def on_slash_command_error(inter: disnake.AppCmdInter, error: Exception):
#    await inter.send('An unknown error occurred while proccessing your request. Please try again.')


bot.run(config.BOT_TOKEN)
