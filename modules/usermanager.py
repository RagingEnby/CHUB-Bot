from typing import Optional

import aiohttp
import disnake

import datatypes
from modules import datamanager, mojang

LinkedUsers = datamanager.DictManager('storage/linkedusers.json')
BannedUsers = datamanager.DictManager('storage/bannedusers.json')


async def log_link(member: disnake.Member, player: datatypes.MinecraftPlayer):
    LinkedUsers.data[player.uuid] = member.id
    await LinkedUsers.save()


async def log_unlink(player: datatypes.MinecraftPlayer):
    if player.uuid in LinkedUsers.data:
        del LinkedUsers.data[player.uuid]
        await LinkedUsers.save()


async def get_linked_player(member: disnake.Member | int, session: Optional[aiohttp.ClientSession] = None) -> Optional[datatypes.MinecraftPlayer]:
    if isinstance(member, disnake.Member):
        member = member.id
    for uuid, discord_id in LinkedUsers.items():
        if discord_id == member:
            return await mojang.get(uuid, session=session)
    return None


async def is_linked(member: disnake.Member | int) -> bool:
    return await get_linked_player(member) is not None
    

async def log_ban(member: disnake.Member | int, reason: Optional[str]):
    if isinstance(member, disnake.Member):
        member = member.id
    player = await get_linked_player(member)
    if player is None:
        return None
    BannedUsers.data[player.uuid] = (str(member) + ' | ' + reason) if reason else str(member) # type: ignore
    await BannedUsers.save()


def is_banned(player: datatypes.MinecraftPlayer) -> tuple[bool, Optional[str]]:
    return player.uuid in BannedUsers, BannedUsers.get(player.uuid)
