import asyncio
from contextlib import suppress
from typing import Optional

import aiohttp
import disnake
import requests

from modules import asyncreqs, hypixelapi, mojang, usermanager

ITEMS: dict[str, str] = requests.get('https://api.ragingenby.dev/skyblock/item_ids').json()['items']
AUTOCOMPLETE_IGN_CACHE: dict[str, list[str]] = {}
PROFILE_NAMES_CACHE: dict[str, list[str]] = {}


async def ign(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    user_input = user_input.lower().strip().replace('/', '').replace(' ', '_')
    print(f'IGN Autocomplete > [{inter.user.name}]  {user_input}')
    if not user_input:
        # EASTER EGG: These are all 5 CHUB admins :3
        return [
            "RagingEnby",
            "TGWaffles",
            "_Foe",
            "Vinush",
            "Bibby"
        ]

    # try to use locally saved response first if possible
    if user_input in AUTOCOMPLETE_IGN_CACHE:
        return AUTOCOMPLETE_IGN_CACHE[user_input]

    """# API has a temp minimum of 3 chars to speed up the process
    if len(user_input) < 3:
        AUTOCOMPLETE_IGN_CACHE[user_input] = [user_input]
        return AUTOCOMPLETE_IGN_CACHE[user_input]"""

    with suppress(asyncio.TimeoutError):
        response = await asyncio.wait_for(
            asyncreqs.get('https://api.ragingenby.dev/stem/' + user_input),
            # timeout so low because 1. people type fast 2. discord is unforgiving asf
            # with their timeouts on autocomplete
            timeout=3
        )
        if response.status != 200:
            AUTOCOMPLETE_IGN_CACHE[user_input] = [user_input]
            return AUTOCOMPLETE_IGN_CACHE[user_input]
        AUTOCOMPLETE_IGN_CACHE[user_input] = [
            player['name'] for player in await response.json()
        ]
        return AUTOCOMPLETE_IGN_CACHE[user_input]


async def banned(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    print(f'Banned Autocomplete > [{inter.user.name}]  {user_input}')
    best_results = [user for user in usermanager.BannedUsers if user.startswith(user_input.lower())]
    other_results = [user for user in usermanager.BannedUsers if user_input.lower() in user]
    return (best_results + other_results)[0:25]


async def profile(inter: disnake.AppCmdInter, user_input: str, ign: Optional[str] = None) -> list[str]:
    print(f'Profile Autocomplete > [{inter.user.name}]  {user_input}')
    if not ign:
        return []
    ign = ign.lower()
    if ign in PROFILE_NAMES_CACHE:
        return PROFILE_NAMES_CACHE[ign]
    async with aiohttp.ClientSession() as session:
        player = await mojang.get(ign, session=session)
        if not player:
            return []
        profile_names = await hypixelapi.get_profile_names(
            uuid=player.uuid,
            session=session,
            allowed_types=['normal']
        )
        PROFILE_NAMES_CACHE[player.name.lower()] = [p.title() for p in profile_names]
        return PROFILE_NAMES_CACHE[player.name.lower()]


async def buyer_profile(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    return await profile(inter, user_input, inter.filled_options.get('buyer'))


async def seller_profile(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    return await profile(inter, user_input, inter.filled_options.get('seller'))
