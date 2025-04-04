from typing import Optional

import aiohttp
import disnake

import datatypes
from modules import datamanager, mojang

linked_users = datamanager.DictManager('storage/linkedusers.json')
banned_users = datamanager.DictManager('storage/bannedusers.json')


async def log_unlink(player: datatypes.MinecraftPlayer|str):
    if isinstance(player, datatypes.MinecraftPlayer):
        player = player.uuid
    if player in linked_users.data:
        del linked_users[player]


def get_linked_uuid(member: disnake.Member | int) -> Optional[str]:
    if isinstance(member, disnake.Member):
        member = member.id
    for uuid, discord_id in linked_users.data.items():
        if discord_id == member:
            return uuid


async def get_linked_player(member: disnake.Member | int, session: Optional[aiohttp.ClientSession] = None) -> Optional[datatypes.MinecraftPlayer]:
    uuid = get_linked_uuid(member)
    if not uuid:
        return None
    return await mojang.get(uuid, session=session)
    

async def log_ban(member: disnake.Member | int, reason: Optional[str] = None):
    if isinstance(member, disnake.Member):
        member = member.id
    player = await get_linked_player(member)
    if player is None:
        return None
    banned_users[player.uuid] = (str(member) + ' | ' + reason) if reason else 'No reason given.' # type: ignore


async def log_unban(member: disnake.Member | int):
    if isinstance(member, disnake.Member):
        member = member.id
    uuids = [uuid for uuid, reason in banned_users.items() if reason.startswith(f"{member} | ")]
    for uuid in uuids:
        del banned_users[uuid]
         