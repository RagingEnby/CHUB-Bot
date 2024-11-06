from typing import Optional

import aiohttp

import datatypes
from modules import asyncreqs


async def get(
    identifier: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[datatypes.MinecraftPlayer]:
    response = await asyncreqs.get(
        'https://api.ragingenby.dev/player/' + identifier,
        session=session
    )
    data = await response.json()
    if 'id' in data and 'name' in data:
        return datatypes.MinecraftPlayer.from_dict(data)
    return None
