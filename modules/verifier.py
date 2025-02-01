import json
import time
from contextlib import suppress
from typing import Optional
import asyncio

import aiohttp
import disnake
from disnake.errors import Forbidden

import config
import datatypes
from modules import datamanager, hypixelapi, misc, mojang, roles, usermanager


async def log_verification(inter: disnake.AppCmdInter, player: datatypes.MinecraftPlayer,
                           member: disnake.Member, session: aiohttp.ClientSession):
    embed = await misc.make_backgroundcheck_embed(player, member, session=session)
    channel = inter.bot.get_channel(config.VERIFICATION_LOG_CHANNEL)
    await channel.send(embed=embed)


async def get_player_data(uuid: str, session: Optional[aiohttp.ClientSession] = None):
    return await hypixelapi.ensure_data("/player", {"uuid": uuid}, session=session)


async def get_linked_discord(player: datatypes.MinecraftPlayer|str, session: Optional[aiohttp.ClientSession] = None, player_data: Optional[dict]=None) -> \
        Optional[str]:
    if isinstance(player, datatypes.MinecraftPlayer):
        player = player.uuid
    data = player_data or await get_player_data(uuid=player, session=session)
    if 'player' in data:
        data = data['player']
    return data.get('socialMedia', {}).get('links', {}).get('DISCORD', None)


async def get_item_roles(player: datatypes.MinecraftPlayer, session: Optional[aiohttp.ClientSession] = None) -> list[int]:
    item_roles = []
    items, applied_items = await misc.get_player_items(player.uuid, session=session)
    item_ids = [item['ExtraAttributes']['id'] for item in items.values()] + applied_items
    pets = [json.loads(item['ExtraAttributes']['petInfo']) for item in items.values() if item.get('ExtraAttributes', {}).get('id') == 'PET' and 'petInfo' in item['ExtraAttributes']]
    pet_skins = list(set(['PET_SKIN_' + pet['skin'] for pet in pets if pet.get('skin')]))
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
    # IDEs get mad if you dont do this:
    if member is None:
        return
        
    if player is None:
        player = await usermanager.get_linked_player(member, session=session)
    if player is None:
        print(member.name, 'might have an invalid account linked')
        return
    player_data = await get_player_data(player.uuid, session=session)
    discord = await get_linked_discord(player, player_data=player_data)
    if discord is None or str(discord).lower() != member.name.lower():
        del usermanager.linked_users[player.uuid]
        return await remove_verification(member)
        
    with suppress(disnake.NotFound):
        roles = [config.VERIFIED_ROLE]

        item_roles, misc_roles = await asyncio.gather(
            get_item_roles(player, session=session),
            get_misc_roles(player, player_data=player_data)
        )
        roles.extend(item_roles)
        roles.extend(misc_roles)

        if member.display_name != player.name:
            with suppress(Forbidden):
                await member.edit(nick=player.name)
        tasks = []
        if player.name in config.guild_members and config.GUILD_MEMBER_ROLE in [role.id for role in member.roles]:
            tasks.append(member.remove_roles(
                disnake.Object(config.GUILD_MEMBER_ROLE),
                reason="Not Guild Member"
            ))

        tasks.append(member.add_roles(
            *[disnake.Object(role) for role in roles],
            reason="Auto Roles")
        )
        await asyncio.gather(*tasks)
        


async def remove_verification(member: disnake.Member):
    to_remove = [disnake.Object(role) for role in config.REQUIRES_VERIFICATION
                 if member.get_role(role)]
    with suppress(disnake.NotFound, disnake.Forbidden):
        await asyncio.gather(
            member.remove_roles(*to_remove, reason="Unverified"),
            member.edit(nick=None)
        )
    

async def verify_command(inter: disnake.AppCmdInter, ign: str, member: Optional[disnake.Member] = None):
    member: disnake.Member = member or inter.user # type: ignore
    async with aiohttp.ClientSession() as session:
        linked_player = await usermanager.get_linked_player(member, session=session) # type: ignore
        if linked_player:
            return await inter.send(embed=misc.make_error(
                "Already Verified",
                "Your discord account is already linked. Use /unverify first."
            ))

        player = await mojang.get(ign, session=session)

        if player is None:
            return await inter.send(embed=misc.make_error(
                "Invalid IGN",
                f"The IGN [{disnake.utils.escape_markdown(ign)}]"
                f"(<https://namemc.com/profile/{disnake.utils.escape_markdown(ign)}>) "
                f"does not belong to any Minecraft player!."
            ))

        discord = await get_linked_discord(player, session=session)
        if str(discord).lower() != member.name.lower(): # type: ignore
            return await inter.send(embed=misc.make_error(
                "Discord Mismatch",
                {
                    "IGN": player.name,
                    "Your Discord": member.name, # type: ignore
                    "Linked Discord": discord
                }
            ))

        # bot ONLY gets here if the user has put in THEIR account
        ban_reason = usermanager.banned_users.get(player.uuid)
        if ban_reason and not ban_reason.startswith(str(member.id)):
            embed = misc.make_error(
                "Ban Evader Detected",
                "You've been detected ban evading. Please join the appeals server if this is incorrect."
            )
            content = "https://discord.gg/6VAAvW7pAm"
            await inter.send(content, embed=embed)
            print(f'found a smelly ban evader (ign: {ign}, uuid: {player.uuid}, '
                  f'reason: {reason}, member.id: {member.id})') # type: ignore
            try:
                await inter.user.send(content, embed=embed)
            except Exception as e:
                print(f"couldn't dm ban evading user {member.name} ({member.id}): {e}") # type: ignore
            return await misc.ban_member(inter.bot, member.id, reason) # type: ignore
        elif ban_reason:
            await usermanager.log_unban(member.id)

        usermanager.linked_users.data[player.uuid] = member.id

        await asyncio.gather(
            member.add_roles(disnake.Object(config.VERIFIED_ROLE), reason=f'Verified to {player.name}'),
            update_member(member, session=session) # type: ignore
        )

        with suppress(disnake.NotFound, disnake.Forbidden):
            await inter.send(embed=misc.make_success(title="Successfully Linked!"))
    await log_verification(inter, player, member, session=session)


async def unverify_command(inter: disnake.AppCmdInter, member: Optional[disnake.Member] = None):
    member: disnake.Member = member or inter.user # type: ignore
    async with aiohttp.ClientSession() as session:
        player = await usermanager.get_linked_player(member, session=session) # type: ignore
        if not player:
            return await inter.send(embed=misc.make_error(
                "Not Verified",
                "You are not verified. Use the /verify command to verify your account."
            ))
        asyncio.gather(
            
        )
        await asyncio.gather(
            usermanager.log_unlink(player),
            remove_verification(member)
        )
        await inter.send(embed=misc.make_success('successfully unlinked!'))
    

async def update_command(inter: disnake.AppCmdInter, member: Optional[disnake.Member] = None):
    before = time.time()
    member: disnake.Member = member or inter.user # type: ignore
    async with aiohttp.ClientSession() as session:
        player = await usermanager.get_linked_player(member, session=session)
        if not player:
            return await inter.send(embed=misc.make_error(
                "Unverified",
                "Please verify using the /verify command first."
            ))
        
        await update_member(
            member=member,
            player=player,
            session=session
        )
        after = time.time()
        await inter.send(embed=misc.make_success(
            "successfully updated!",
            f"Took `{round(after - before, 2)}s`!"
        ))
        