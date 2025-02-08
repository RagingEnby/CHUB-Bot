from typing import Optional
import asyncio

import aiohttp

import datatypes
from modules import asyncreqs
import config


async def get(
    identifier: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[datatypes.MinecraftPlayer]:
    url = 'https://api.ragingenby.dev/player/' + identifier\
            if 'https://' not in identifier\
            else identifier
    
    response = await asyncreqs.get(
        url,
        session=session
    )
        
    data = await response.json()
    if 'id' in data and 'name' in data:
        return datatypes.MinecraftPlayer.from_dict(data)
    print(f'mojang.get({identifier}) > {data}')
    return None
