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


async def log_unlink(player: datatypes.MinecraftPlayer|str):
    if isinstance(player, datatypes.MinecraftPlayer):
        player = player.uuid
    if player in LinkedUsers.data:
        del LinkedUsers[player]


async def get_linked_player(member: disnake.Member | int, session: Optional[aiohttp.ClientSession] = None, return_uuid: bool=False) -> Optional[datatypes.MinecraftPlayer|str]:
    if isinstance(member, disnake.Member):
        member = member.id
    for uuid, discord_id in LinkedUsers.items():
        if discord_id == member:
            if return_uuid:
                return uuid
            return await mojang.get(uuid, session=session)


async def is_linked(member: disnake.Member | int) -> bool:
    return await get_linked_player(member, return_uuid=True) is not None
    

async def log_ban(member: disnake.Member | int, reason: Optional[str]):
    if isinstance(member, disnake.Member):
        member = member.id
    player = await get_linked_player(member)
    if player is None:
        return None
    BannedUsers[player.uuid] = (str(member) + ' | ' + reason) if reason else str(member) # type: ignore
    await BannedUsers.save()


async def log_unban(member: disnake.Member | int):
    if isinstance(member, disnake.Member):
        member = member.id
    uuids = [uuid for uuid, reason in BannedUsers.items() if reason.startswith(f"{member} | ")]
    for uuid in uuids:
        del BannedUsers.data[uuid]


def is_banned(player: datatypes.MinecraftPlayer) -> tuple[bool, Optional[str]]:
    return player.uuid in BannedUsers, BannedUsers.get(player.uuid)
