from contextlib import suppress
import json
import time
from typing import Optional

import aiofiles
import aiohttp
import disnake
from disnake.errors import Forbidden
from requests.sessions import SessionRedirectMixin

import config
import datatypes
from modules import hypixelapi
from modules import misc
from modules import mojang
from modules import roles
from modules import usermanager


async def log_verification(inter: disnake.AppCmdInter, player: datatypes.MinecraftPlayer,
                           member: disnake.Member, session: aiohttp.ClientSession):
    params = {"key": config.HYPIXEL_API_KEY, "keyType": "HYPIXEL"}
    async with session.get(f'https://api.ragingenby.dev/backgroundcheck/{player.uuid}', params=params) as response:
        data = await response.json()
        description = [
            f"**Linked To:** {member.mention}",
            f"**First Login:** <t:{round(data['firstLogin']) // 1000}> (<t:{round(data['firstLogin']) // 1000}:R>)",
            f"**Possible Alts:** `{', '.join([disnake.utils.escape_markdown(player['name']) for player in data['possibleAlts']]) if data['possibleAlts'] else 'None'}`"
        ]
        embed = disnake.Embed(
            description='\n'.join(description)
        )
        embed.set_author(
            name=data['rankname'],
            icon_url="https://mc-heads.net/avatar/" + player.uuid
        )
        embed.set_footer(
            text=f"{member.name} ({member.id})",
            icon_url=member.display_avatar.url
        )
        for profile in data['skyblockProfiles']:
            value = [
                f"Selected: {':white_check_mark:' if profile['selected'] else ':x:'}",
                f"Profile Type: `{profile['game_mode']}`",
                f"Networth: `{misc.numerize(profile['networth'])}`",
                f"Level: `{profile['sbLevel']}`",
                f"Fairy Souls: `{profile['fairySouls']}`",
            ]
            for weight_name, weight_value in profile['weight'].items():
                value.append(f"-# {weight_name.title()} Weight: `{round(weight_value, 2)}`")
            embed.add_field(
                name=profile['cute_name'],
                value='\n'.join(value)
            )
    channel = inter.bot.get_channel(config.VERIFICATION_LOG_CHANNEL)
    await channel.send(embed=embed)


async def get_player_data(uuid: str, session: Optional[aiohttp.ClientSession] = None):
    return await hypixelapi.ensure_data("/player", {"uuid": uuid}, session=session)


async def get_linked_discord(player: datatypes.MinecraftPlayer, session: Optional[aiohttp.ClientSession] = None, player_data: Optional[dict]=None) -> \
        Optional[str]:
    data = await get_player_data(uuid=player.uuid, session=session) or player_data
    return data.get('player', {}).get('socialMedia', {}).get('links', {}).get('DISCORD', None)


async def get_item_roles(player: datatypes.MinecraftPlayer, session: Optional[aiohttp.ClientSession] = None) -> list[int]:
    item_roles = []
    items = await misc.get_player_items(player.uuid, session=session)
    item_ids = [item['ExtraAttributes']['id'] for item in items.values()]
    # really shittily made debug statement, ignore it:
    for item in items:
        if isinstance(item, str):
            print(json.dumps(item, indent=2))
    pets = [json.loads(item['ExtraAttributes']['petInfo']) for item in items if item.get('ExtraAttributes', {}).get('id') == 'PET']
    pet_skins = list(set(['PET_SKIN_' + pet['skin'] for pet in pets if pet['skin']]))
    item_ids.extend(pet_skins)
    item_ids = list(set(item_ids)) # remove duplicates
    for item_id in item_ids:
        if item_id in config.ITEM_ID_ROLES:
            item_roles.append(config.ITEM_ID_ROLES[item_id])
            
    for req_item_ids, role_id in config.ITEM_ID_ROLES.items():
        if ',' not in req_item_ids:
            continue
        req_item_ids = req_item_ids.split(',')
        if all(req_item_id in item_ids for req_item_id in req_item_ids):
            item_roles.append(role_id)

            
    item_roles.extend(await roles.get_checker_roles(list(items.values())))
    item_roles = list(set(item_roles)) # remove duplicates
    return item_roles


async def give_item_roles(member: disnake.Member, player: Optional[datatypes.MinecraftPlayer] = None,
                          session: Optional[aiohttp.ClientSession] = None):
    if not player:
        player = await usermanager.get_linked_player(member)
    if not player:
        return
    deserved_roles = await get_item_roles(player, session=session)
    
    try:
        await member.add_roles(*[disnake.Object(role) for role in deserved_roles], reason="Auto Item Roles")
    except disnake.errors.NotFound:
        pass


async def get_misc_roles(player: datatypes.MinecraftPlayer, player_data: dict) -> list[int]:
    roles = []
    if player.uuid in config.guild_members:
        roles.append(config.GUILD_MEMBER_ROLE)
    rank = player_data.get('player', {}).get('rank')
    if rank in config.RANK_ROLES:
        roles.append(config.RANK_ROLES[rank])
    return roles


async def update_member(member: disnake.Member, player: Optional[datatypes.MinecraftPlayer] = None,
                        session: Optional[aiohttp.ClientSession] = None):
    if member is None:
        return
    if player is None:
        player = await usermanager.get_linked_player(member)
    if player is None:
        print(member.name, 'might have an invalid account linked')
        return
    player_data = await get_player_data(player.uuid, session=session)
    discord = await get_linked_discord(player, player_data=player_data)
    if discord is None or str(discord).lower() != member.name.lower():
        await remove_verification(member)
        await usermanager.log_unlink(player)
        return
        
    with suppress(disnake.NotFound):
        roles = [config.VERIFIED_ROLE]

        roles.extend(await get_item_roles(player, session=session))
        roles.extend(await get_misc_roles(player, player_data=player_data))

        if member.display_name != player.name:
            with suppress(Forbidden):
                await member.edit(nick=player.name)
        if player.name in config.guild_members and config.GUILD_MEMBER_ROLE in [role.id for role in member.roles]:
            await member.remove_roles(disnake.Object(config.GUILD_MEMBER_ROLE), reason="Not Guild Member")

        await member.add_roles(*[disnake.Object(role) for role in roles], reason="Auto Roles")
        


async def remove_verification(member: disnake.Member):
    to_remove = [disnake.Object(role) for role in config.REQUIRES_VERIFICATION if
                 role in [role.id for role in member.roles]]
    await member.remove_roles(*to_remove, reason="Unverified")
    try:
        await member.edit(nick=None)
    except Forbidden:
        pass


async def verify_command(inter: disnake.AppCmdInter, ign: str, member: Optional[disnake.Member] = None):
    if member is None:
        member = inter.user
    async with aiohttp.ClientSession() as session:
        if await usermanager.is_linked(member.id):
            return await inter.send(embed=misc.make_error(
                title="already verified",
                description="Your discord account is already linked. Use /unverify first."
            ))

        player = await mojang.get_uuid(ign, session=session)
        if player is None:
            return await inter.send(embed=misc.make_error(
                title="invalid IGN",
                description=f"The IGN [{disnake.utils.escape_markdown(ign)}]"
                            f"(<https://namemc.com/profile/{disnake.utils.escape_markdown(ign)}>) "
                            f"does not belong to any Minecraft player!."
            ))

        discord = await get_linked_discord(player, session=session)
        if str(discord).lower() != member.name.lower():
            return await inter.send(embed=misc.make_error(
                title="discord mismatch",
                description={
                    "IGN": player.name,
                    "Your Discord": member.name,
                    "Linked Discord": discord
                }
            ))

        # bot ONLY gets here if the user has put in THEIR account
        is_banned, reason = await usermanager.is_banned(player)
        if is_banned:
            embed = misc.make_error(
                title="ban evader detected",
                description="You've been detected ban evading. Please reach out to a staff member if this is incorrect."
            )
            await inter.send(embed=embed)
            print(f'found a smelly ban evader (ign: {ign}, uuid: {player.uuid}, reason: {reason}, '
                  f'member.id: {member.id})')
            try:
                await inter.user.send(embed=embed)
            except Exception as e:
                print(f"couldn't dm ban evading user {member.name} ({member.id}): {e}")
            return await misc.ban_member(inter.bot, member.id, reason)

        try:
            await member.add_roles(disnake.Object(config.VERIFIED_ROLE), reason=f'Verified to {player.name}')
        except Forbidden:
            print('do not have permission to add roles')

        await usermanager.log_link(member, player)

        await update_member(member, session=session)

        try:
            await inter.send(embed=misc.make_success(title="Successfully Linked!"))
        except disnake.NotFound:
            # this just means the interaction timed out (likely due to hypixel rate limits)
            pass

        await log_verification(inter, player, member, session=session)


async def unverify_command(inter: disnake.AppCmdInter, member: Optional[disnake.Member] = None):
    if member is None:
        member = inter.user
    if not await usermanager.is_linked(member.id):
        return await inter.send('You are not linked.')
    player = await usermanager.get_linked_player(member)
    if player is None:
        return await inter.send(embed=misc.make_error(
            'nonexistent player linked',
            'You are linked to a nonexistent player.\n'
            f'Please message <@{config.BOT_DEVELOPER_ID}> (@ragingenby) for assistance.'
        ))
    await remove_verification(member)
    await usermanager.log_unlink(player)
    await inter.send('Successfully unlinked')


async def update_command(inter: disnake.AppCmdInter, member: Optional[disnake.Member] = None):
    before = time.time()
    if member is None:
        member = inter.user
    if not await usermanager.is_linked(member.id):
        return await inter.send(embed=misc.make_error(
            'not linked',
            'Please verify using the /verify command first.'
        ))
    await update_member(member)
    after = time.time()
    await inter.send(embed=misc.make_success(
        "successfully updated!",
        f"Took `{round(after - before, 2)}s`!"
    ))
