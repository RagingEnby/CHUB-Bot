from typing import Optional
import aiohttp
import datatypes
import aiohttp.client_exceptions

from modules import asyncreqs


async def get_uuid(name: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[datatypes.MinecraftPlayer]:
    url = 'https://api.mojang.com/users/profiles/minecraft/' + name
    response = await asyncreqs.get(url, session=session)
    return datatypes.MinecraftPlayer.from_dict(await response.json())


async def get_name(uuid: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[datatypes.MinecraftPlayer]:
    url = 'https://sessionserver.mojang.com/session/minecraft/profile/' + uuid
    response = await asyncreqs.get(url, session=session)
    return datatypes.MinecraftPlayer.from_dict(await response.json())
