from typing import Optional
import asyncio
import disnake
import json

from modules import asyncreqs

AUTOCOMPLETE_IGN_CACHE: dict[str, list[str]] = {}


async def ign(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    user_input = user_input.lower().strip().replace('/', '').replace(' ', '_')
    print(f'IGN Autocomplete > [{inter.user.name}]  {user_input}')
    if not user_input:
        # EASTER EGG: These are all 5 CHUB admins :3
        return list(set([
            inter.author.display_name, # this is just the authors ign 99% of the time
            "RagingEnby",
            "TGWaffles",
            "_Foe",
            "Vinush",
            "Bibby"
        ]))

    # try to use locally saved response first if possible
    if user_input in AUTOCOMPLETE_IGN_CACHE:
        return AUTOCOMPLETE_IGN_CACHE[user_input]

    """# API has a temp minimum of 3 chars to speed up the process
    if len(user_input) < 3:
        AUTOCOMPLETE_IGN_CACHE[user_input] = [user_input]
        return AUTOCOMPLETE_IGN_CACHE[user_input]"""

    try:
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
    except asyncio.TimeoutError:
        print('Timeout error for stem', user_input)
        AUTOCOMPLETE_IGN_CACHE[user_input] = [user_input]
        return AUTOCOMPLETE_IGN_CACHE[user_input]


async def profile(inter: disnake.AppCmdInter, ign: Optional[str] = None) -> list[str]:
    if not ign:
        return []
    return [
        ign,
        json.dumps(inter.filled_options)
    ]
    print(inter.filled_options)
    return [
        "test command",
        "why are you using this",
        "aaaaaaaaaaaaa"
    ]


async def buyer_profile(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    return await profile(inter, inter.filled_options.get('buyer'))


async def seller_profile(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    return await profile(inter, inter.filled_options.get('seller'))
