from typing import Optional, Literal
from enum import Enum
import aiohttp
import datatypes
import aiohttp.client_exceptions

from modules import asyncreqs

class Api(Enum):
    RAGING = 1
    MOJANG = 2


def make_url(identifier: str, api: Api) -> str:
    if api == Api.MOJANG and len(identifier) >= 32:
        # identifier is a UUID, use mojang's UUID -> Name API
        url = 'https://sessionserver.mojang.com/session/minecraft/profile/'
    elif api == Api.MOJANG and len(identifier) < 32:
        # identifier is a Name, use mojang's Name -> UUID API
        url = 'https://api.mojang.com/users/profiles/minecraft/'
    else:
        # identifier is a Name or UUID, use ragingenby's Name <-> UUID API
        url = 'https://api.ragingenby.dev/player/'
    return url + identifier


async def get(identifier: str, session: Optional[aiohttp.ClientSession] = None,
                   api: Api = Api.MOJANG) -> Optional[datatypes.MinecraftPlayer]:
    url = make_url(identifier, api)
    response = await asyncreqs.get(url, session=session)
    try:
        if response.status == 429:
            raise Exception('Rate limited')
        return datatypes.MinecraftPlayer.from_dict(await response.json())
    except Exception as e:
        if api == Api.MOJANG:
            print(f'mojang.get({identifier}, api=Api.MOJANG) raised:', e)
        raise # raise the error if this is from api.ragingenby.dev
