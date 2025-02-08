import json
import asyncio
from typing import Optional

import aiohttp

import datatypes
from modules import asyncreqs

NAME_TO_UUID_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/name/{}"
UUID_TO_NAME_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/{}"


def get_url(identifier: str, raging_api: bool = True) -> str:
    if raging_api:
        return f"https://api.ragingenby.dev/player/{identifier}"
    if len(identifier) > 16:
        return UUID_TO_NAME_URL.format(identifier)
    return NAME_TO_UUID_URL.format(identifier)


async def get(
    identifier: str,
    session: Optional[aiohttp.ClientSession] = None,
    raging_api: bool = True
) -> Optional[datatypes.MinecraftPlayer]:
    url = get_url(identifier)
    try:
        response = await asyncio.wait_for(
            asyncreqs.get(
                url,
                session=session
            ),
            timeout=15
        )
    except asyncio.TimeoutError as e:
        if not raging_api:
            return await get(identifier, session=session, raging_api=True)
        print(f'asyncio.TimeoutError:\ne: {e}\nurl: {url}\nraging_api: {raging_api}')
        raise e
    response = await asyncreqs.get(
        get_url(identifier),
        session=session
    )
        
    data = await response.json()
    if data.get('id') and data.get('name'):
        return datatypes.MinecraftPlayer.from_dict(data)
    print(f'mojang.get({identifier}) > {json.dumps(data)}')
    return None
