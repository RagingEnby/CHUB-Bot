import asyncio
import json
import traceback
from contextlib import suppress
from typing import Optional

import aiohttp
import disnake
from disnake.ext import commands, tasks

import config
import ws
from modules import (
    asyncreqs,
    autocomplete,
    cmdlogger,
    hypixelapi,
    misc,
    mojang,
    tradereport,
    usermanager,
    verifier,
)

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
    ),
    # this restricts slash commands to ONLY work in collector's hub:
    test_guilds=[934240413974417439]
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
    async for msg in verification_channel.history(limit=None): # type: ignore
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
            if audit_ban.target.id == user.id: # type: ignore
                # IDEs don't like this since AuditLogEntry.user isn't always Member, but in this instance it is:
                moderator = audit_ban.user # type: ignore
                break
        channel = bot.get_channel(config.STAFF_CHANNEL)
        await channel.send(f"{(moderator.mention + ' ') if moderator else ''}" # type: ignore
                           f"**{disnake.utils.escape_markdown(ban.user.name)}** ({ban.user.mention}) "
                           f"was banned without reason. Please remember to provide a reason when banning users!!!!")


@bot.event
async def on_guild_channel_create(channel: disnake.abc.GuildChannel):
    if channel.guild.id != config.APPEAL_GUILD_ID:
        return
    if not isinstance(channel, disnake.TextChannel):
        return
    if not channel.name.startswith('ticket-'):
        return
    


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
            error = traceback.format_exc()
            print(f">exec ERROR:\n{error}")
            await message.reply(f"Error while running code:\n```py\n{error}```")
    elif message.channel.id == config.VERIFICATION_CHANNEL and not await bot.is_owner(message.author):
        await asyncio.sleep(60)
        with suppress(disnake.errors.NotFound):
            await message.delete()
    elif message.guild and message.guild.id == config.APPEAL_GUILD_ID and\
    isinstance(message.channel, disnake.TextChannel) and\
    message.channel.name.startswith('ticket-') and\
    message.author.id == config.TICKET_TOOL_ID and 'Welcome' in message.content and\
    len(message.embeds) == 2:
        # this is the welcome message in a ticket, for example:
        # https://i.ragingenby.dev/u/nQpvHm.png
        description = message.embeds[1].description.replace('**', '').replace('```', '').split('\n')
        description = [i.strip() for i in description]
        ign = description[1]
        inputted_ban_reason = description[3]
        inputted_ban_date = description[5]
        player = await mojang.get(ign)
        if player is None:
            return await message.reply(embed=misc.make_error(
                "Invalid IGN",
                f"(<https://namemc.com/profile/{disnake.utils.escape_markdown(ign)}>) "
                "is not a valid Minecraft username."
            ))
        non_staff = [
            m for m in message.channel.members if\
            not m.get_role(config.APPEAL_STAFF_ROLE) and\
            not m.bot
        ]
        if len(non_staff) != 1:
            print("non_staff:", [m.id for m in non_staff])
            return await message.channel.send(f"{config.BOT_DEVELOPER_MENTION} Found multiple (or none) non-staff members, see console for details")
        member = non_staff[0]
        chub = await misc.get_guild(bot)
        ban = None
        async for ban in chub.bans(limit=None):
            if ban.user.id == member.id:
                break
        if ban is None:
            return await message.channel.send(f"{member.mention} I was unable to find your ban, please try rejoining Collector's Hub\nhttps://discord.gg/collectors")
        embed = await misc.make_backgroundcheck_embed(player=player, member=member)
        await message.channel.send(f"{member.mention} was banned from CHUB for reason `{ban.reason}`", embed=embed)
        


@bot.event
async def on_button_click(inter: disnake.MessageInteraction):
    button_type, button_data = inter.component.custom_id.split('|', 1) # type: ignore
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
    description="Report a trade for it to be sent in #recent-sales"
)
async def report_trade_command(
    inter: disnake.AppCmdInter,
    seller: str = misc.ign_param(description='The player who sold the item'),
    buyer: str = misc.ign_param(description='The player who bought the item'),
    date: str = commands.param(description="PLEASE USE DD/MM/YYYY FORMAT"),
    item: str = commands.param(),
    price: str = commands.param(),
    image: disnake.Attachment = commands.param(description="An image of the trade"),
    notes: Optional[str] = commands.param(description="Any notes you want to add", default=None)
):
    await tradereport.report_trade_command(inter, seller, buyer, date, item, price, image, notes)



@bot.slash_command(
    name="test-command",
    description="Test command for /report-trade"
)
async def test_command(
    inter: disnake.AppCmdInter,
    item: str = commands.Param(description='Item traded (one report per unique item)', autocomplete=autocomplete.item),
    value: int = commands.Param(description='Value of the item traded (if more than one quantity, value should be price per unit times quantity)', ge=750000000),
    date: str = commands.Param(description='Date and time of sale in EST (MM/DD/YYYY HH:MM AM/PM)'),
    seller: str = misc.ign_param(description='The player who sold the item'),
    seller_profile: str = misc.profile_param('The profile of the player who sold the item', 'seller'),
    buyer: str = misc.ign_param(description='The player who bought the item'),
    buyer_profile: str = misc.profile_param('The profile of the player who bought the item', 'buyer'),
    image: disnake.Attachment = commands.Param(description='A screenshot of the trade'),
    note: Optional[str] = commands.Param(description='Any extra info about the trade you want to include (OPTIONAL)', default=None),
    screenshot_2: Optional[disnake.Attachment] = commands.Param(description='Extra Screenshot (OPTIONAL)', default=None),
    screenshot_3: Optional[disnake.Attachment] = commands.Param(description='Extra Screenshot (OPTIONAL)', default=None),
    screenshot_4: Optional[disnake.Attachment] = commands.Param(description='Extra Screenshot (OPTIONAL)', default=None),
    screenshot_5: Optional[disnake.Attachment] = commands.Param(description='Extra Screenshot (OPTIONAL)', default=None)
):
    date_obj = misc.parse_date(date)
    if date_obj is None:
        return await inter.send(embed=misc.make_error(
            "Invalid Date",
            f"Please make sure your date is in EST and the uses the format `MM/DD/YYYY HH:MM AM/PM`. for example: `{misc.get_date()}`"
        ))
    async with aiohttp.ClientSession() as session:
        seller_profile = seller_profile.lower()
        buyer_profile = buyer_profile.lower()

        seller_player, buyer_player = await asyncio.gather(
            mojang.get(seller, session=session),
            mojang.get(buyer, session=session)
        )
        if not seller_player or not buyer_player:
            return await inter.send(embed=misc.make_error(
                "Invalid Player(s)",
                "One or more inputted IGNs are invalid. Please double check your spelling and try again."
            ))
        seller_profiles, buyer_profiles = await asyncio.gather(
            hypixelapi.get_profile_names(seller_player.uuid, session=session, allowed_types=['normal']),
            hypixelapi.get_profile_names(buyer_player.uuid, session=session, allowed_types=['normal'])
        )
        if seller_profile not in seller_profiles or buyer_profile not in buyer_profiles:
            return await inter.send(embed=misc.make_error(
                "Invalid Profile(s)",
                "One or more inputted profile names are invalid. Please double check your spelling and try again."
            ))

    await inter.response.send_message(f"```json\n{json.dumps(inter.filled_options, indent=2)}```")




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
            "Staff Role",
            f"The bot is manually set to not give out the <@{config.STAFF_ROLE}> role."
        ))
    try:
        await member.add_roles(role)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "No Permissions",
            f"I do not have permissions to give out the {role.mention} role."
        ))
    await inter.send(embed=misc.make_success(
        "Success",
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
            "No Permissions",
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
            "No Ban Reason",
            "You must provide a ban reason."
        ))

    reason = reason + f" | Banned by {inter.author.name} ({inter.author.id})"
    try:
        await member.send(f'You were banned from Collector\'s Hub for reason `{disnake.utils.escape_markdown(reason)}`\nYou can appeal your ban at https://discord.gg/xzPzwR6AFu')
    except Exception as e:
        print("unable to dm member during ban:", member.name, member.id, e)
    try:
        await member.ban(reason=reason)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "No Permissions",
            f"I do not have permissions to ban {member.mention}."
        ))
    await inter.send(embed=misc.make_success(
        "success",
        f"Banned {member.mention} for reason `{reason}`."
    ))


@moderation.sub_command(
    name="kick",
    description="Kick a user from the server"
)
async def moderation_kick_command(inter: disnake.AppCmdInter, member: disnake.Member, reason: str):
    if not await misc.validate_mod_cmd(inter, member.top_role):
        return
    if not reason.replace(' ', ''):
        return await inter.send(embed=misc.make_error(
            "No Kick Reason",
            "You must provide a kick reason."
        ))
    reason = reason + f" | Kicked by {inter.author.name} ({inter.author.id})"
    try:
        await member.send(f'You were kicked from Collector\'s Hub for reason `{disnake.utils.escape_markdown(reason)}`')
    except Exception as e:
        print("unable to dm member during kick:", member.name, member.id, e)
    try:
        await member.kick(reason=reason)
    except disnake.Forbidden:
        return await inter.send(embed=misc.make_error(
            "No Permissions",
            f"I do not have permissions to kick {member.mention}."
        ))
    await inter.send(embed=misc.make_success(
        "Success",
        f"Kicked {member.mention} for reason `{reason}`."
    ))




# noinspection DuplicatedCode
@moderation.sub_command(
    name="unblacklist",
    description="Unblacklist a Minecraft player from the server"
)
async def moderation_unblacklist_command(inter: disnake.AppCmdInter, player: str = commands.Param(
    autocomplete=autocomplete.banned,
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
            "Invalid Account",
            f"There is no account with the UUID `{disnake.utils.escape_markdown(player)}`!"
        ))

    if player_obj.uuid not in usermanager.BannedUsers:
        return await inter.send(embed=misc.make_error(
            "Not Banned",
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
            "Invalid Account",
            f"There is no account with the UUID `{disnake.utils.escape_markdown(player)}`!"
        ))

    if player_obj.uuid in usermanager.BannedUsers:
        return await inter.send(embed=misc.make_error(
            "Already Bbanned",
            f"Account `{disnake.utils.escape_markdown(player)}` is already blacklisted."
        ))
    usermanager.BannedUsers[player_obj.uuid] = f"{player_obj.uuid} | Banned by {inter.author.name} ({inter.author.id})"
    await usermanager.BannedUsers.save()


@moderation.sub_command(
    name="bulk-blacklist",
    description="Blacklist a group of players at once"
)
async def moderation_bulk_blacklist_command(inter: disnake.AppCmdInter, file: disnake.Attachment, reason: str):
    return await inter.response.send_message(embed=misc.make_error(
        "Broken Command",
        "This command is broken and I haven't bothered fixing it because afaik, "
        "it's not needed atm. If you have a use case for this command, ping "
        "RagingEnby and I'll fix it."
    ))
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


@moderation.sub_command(
    name="backgroundcheck",
    description="Sends an embed with some brief info about a player"
)
async def moderation_backgroundcheck_command(inter: disnake.AppCmdInter, member: disnake.Member):
    if not await misc.validate_mod_cmd(inter):
        return
    async with aiohttp.ClientSession() as session:
        player = await usermanager.get_linked_player(member, session=session)
        if player is None:
            return await inter.send(embed=misc.make_error(
                "Unverified",
                "The member you tried to background check is not verified."
            ))
        embed = await misc.make_backgroundcheck_embed(
            player=player,
            member=member,
            session=session
        )
        await inter.send(embed=embed)


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
        "Sell your Crystal/Fairy armor here!\nhttps://discord.gg/crystalcafe")


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
            await asyncio.sleep(3.5)  # rate limit sucks ass


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



@tasks.loop(seconds=6000)
async def update_constants_task():
    items_response = await asyncreqs.get('https://api.ragingenby.dev/skyblock/item_ids')
    items_data = await items_response.json()
    autocomplete.ITEMS = items_data['items']


TSKS.append(update_constants_task)


@tasks.loop(seconds=30)
async def ensure_tasks_working():
    broken_tasks = [tsk for tsk in TSKS if not tsk.is_running()]
    if not broken_tasks:
        return
    channel = bot.get_channel(config.BOT_DEV_CHANNEL)
    formatted_tasks = '\n'.join([str(tsk) for tsk in broken_tasks])
    await channel.send(f"{config.BOT_DEVELOPER_MENTION} `{len(broken_tasks)}` tasks broke:\n```{formatted_tasks}```") # type: ignore
    for tsk in broken_tasks:
        tsk.start()


TSKS.append(ensure_tasks_working)

# @bot.event
# async def on_slash_command_error(inter: disnake.AppCmdInter, error: Exception):
#    await inter.send('An unknown error occurred while proccessing your request. Please try again.')


bot.run(config.BOT_TOKEN)
