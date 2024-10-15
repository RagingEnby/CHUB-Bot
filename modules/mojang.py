from typing import Optional, Literal
import aiohttp
import datatypes
import aiohttp.client_exceptions

from modules import asyncreqs

Api = Literal['mojang', 'ragingenby']


async def get_uuid(name: str, session: Optional[aiohttp.ClientSession] = None,
                   api: Api = 'mojang') -> Optional[datatypes.MinecraftPlayer]:
    url = ('https://api.mojang.com/users/profiles/minecraft/'
           if api == 'mojang' else 'https://api.ragingenby.dev/player/') + name
    response = await asyncreqs.get(url, session=session)
    if response.status == 429 and api == 'mojang':
        return await get_uuid(name, session=session, api='ragingenby')
    return datatypes.MinecraftPlayer.from_dict(await response.json())


async def get_name(uuid: str, session: Optional[aiohttp.ClientSession] = None,
                   api: Api = 'mojang') -> Optional[datatypes.MinecraftPlayer]:
    url = ('https://sessionserver.mojang.com/session/minecraft/profile/'
           if api == 'mojang' else 'https://api.ragingenby.dev/player/') + uuid
    response = await asyncreqs.get(url, session=session)
    if response.status == 429 and api == 'mojang':
        return await get_uuid(uuid, session=session, api='ragingenby')
    return datatypes.MinecraftPlayer.from_dict(await response.json())
