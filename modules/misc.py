import asyncio
import json
import random
from typing import Optional, Any

import aiofiles
import aiohttp
import disnake
from disnake.ext import commands

import config
from modules import asyncreqs, hypixelapi, parser

BOT_CLASS = commands.InteractionBot | commands.Bot | commands.AutoShardedBot
AUTOCOMPLETE_IGN_CACHE: dict[str, list[str]] = {}


async def get_user_from_name(bot: BOT_CLASS, name: str) -> Optional[disnake.Member]:
    for member in bot.get_guild(config.GUILD_ID).members:
        if member.name == name:
            return member
    return None


async def get_guild(bot: BOT_CLASS) -> disnake.Guild:
    return bot.get_guild(config.GUILD_ID)


async def get_members(bot: BOT_CLASS) -> list[disnake.Member]:
    guild = await get_guild(bot)
    return guild.members


async def get_member(bot: BOT_CLASS, user_id: int) -> Optional[disnake.Member]:
    guild = await get_guild(bot)
    return guild.get_member(user_id)


async def get_member_dict(bot: BOT_CLASS) -> dict[int, disnake.Member]:
    members = await get_members(bot)
    return {member.id: member for member in members}


async def get_role(bot: BOT_CLASS, role_id: int) -> Optional[disnake.Role]:
    guild = await get_guild(bot)
    return guild.get_role(role_id)


async def ban_member(bot: BOT_CLASS, user_id: int, reason: Optional[str] = None):
    guild = await get_guild(bot)
    await guild.ban(disnake.Object(user_id), reason=reason)


async def get_player_items(uuid: str, session: Optional[aiohttp.ClientSession] = None) -> dict[str, dict]:
    uuid = uuid.replace('-', '')
    profiles_data = await hypixelapi.ensure_data('/skyblock/profiles', {"uuid": uuid}, session=session)
    if not profiles_data.get('profiles'):
        return {}
    if not profiles_data:
        return {}
    for profile in profiles_data['profiles']:
        if 'game_mode' not in profile:
            print('profile', profile['profile_id'], 'is missing game_mode')
    museum_datas = await asyncio.gather(*[
        hypixelapi.ensure_data('/skyblock/museum', {"profile": profile['profile_id']}, session=session)
        for profile in profiles_data['profiles']
        if should_scan_museum(profile['game_mode'], profile['members'].get(uuid, {}))
    ])
    inventories = await parser.get_inventories(profiles_data)
    museum_inventories = await parser.get_museum_inventories(profiles=museum_datas)
    items = {}
    for inventory in inventories:
        for container_items in inventory['parsed'].values():
            for item in container_items:
                if not item.get('ExtraAttributes', {}).get('uuid'):
                    continue
                items[item['ExtraAttributes']['uuid']] = item
    #print(json.dumps(museum_inventories, indent=2))
    for museum_inventory in museum_inventories:
        for item in museum_inventory['parsed']:
            if not item.get('ExtraAttributes', {}).get('uuid'):
                continue
            items[item['ExtraAttributes']['uuid']] = item

    for profile in profiles_data['profiles']:
        for member in profile['members'].values():
            for pet in member.get('pets_data', {}).get('pets', []):
                id_ = pet.get('uniqueId', pet.get('uuid', pet['type']))
                item = {
                    "ExtraAttributes": {
                        "petInfo": json.dumps(pet),
                        "id": "PET",
                        "uuid": id_
                    }
                }
                items[uuid] = item
    async with aiofiles.open(f'storage/inv/{uuid}.json', 'w') as file:
        await file.write(json.dumps(items, indent=2))
    return items


def add_embed_footer(embed: disnake.Embed) -> disnake.Embed:
    # this exists as a useless function because i will likely in the future add some sort of footer to all embeds,
    # and this function allows me to do that quickly if needed
    return embed


async def randomize_dict_order(input_dict: dict) -> dict:
    keys = list(input_dict.keys())
    random.shuffle(keys)
    return {key: input_dict[key] for key in keys}


async def get_guild_members(session: Optional[aiohttp.ClientSession] = None) -> list[str]:
    data = await hypixelapi.ensure_data("/guild", {"id": config.HYPIXEL_GUILD_ID}, session=session)
    return [member['uuid'] for member in data['guild']['members']]


def make_cmd_str(inter: disnake.AppCmdInter) -> str:
    params_data = {option.name: option.value for option in inter.data.options}
    log_params = " ".join([f"{name}:{value}" for name, value in params_data.items()])
    return f"/{inter.data.name} {log_params}" if log_params else f"/{inter.data.name}"


def format_description(description: Optional[list[str] | str | dict]) -> str:
    if not description:
        return ""
    if isinstance(description, list):
        return '\n'.join(description)
    elif isinstance(description, dict):
        return '\n'.join([f"**{k}:** `{v}`" for k, v in description.items()])
    elif isinstance(description, str):
        return description
    else:
        raise ValueError(f'Invalid description type: {type(description)}')


def make_error(title: str, description: Optional[list[str] | str | dict] = None) -> disnake.Embed:
    description_str = format_description(description)
    embed = disnake.Embed(
        title="Error: " + title.title(),
        color=disnake.Color.red(),
        description=description_str
    )
    embed = add_embed_footer(embed)
    return embed


NOT_GUILD_ERROR: disnake.Embed = make_error(
    "Command Unavailable",
    "This command is not available here. Try using it in the Collector's Hub server or in a different channel."
)


def make_success(title: str, description: Optional[list[str] | str | dict] = None) -> disnake.Embed:
    description_str = format_description(description)
    embed = disnake.Embed(
        title=title.title(),
        description=description_str,
        color=disnake.Color.green()
    )
    embed = add_embed_footer(embed)
    return embed


async def validate_mod_cmd(inter: disnake.AppCmdInter, role: Optional[disnake.Role] = None) -> bool:
    await inter.response.defer()
    if not inter.guild or (inter.guild and inter.guild.id != config.GUILD_ID):
        await inter.send(embed=NOT_GUILD_ERROR)
        return False
    if not inter.author.get_role(config.STAFF_ROLE):
        await inter.send(embed=make_error(
            "no permissions",
            f"You must have the <@&{config.STAFF_ROLE}> role to use this command!"
        ))
        return False
    if role and inter.author.top_role <= role:
        await inter.send(embed=make_error(
            "not allowed",
            f"You are not allowed to give away this role as it is above your top role "
            f"({inter.author.top_role.mention()})"
        ))
    return True


def numerize(num: int | float) -> str:
    num = float('{:.3g}'.format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])


async def autocomplete_ign(inter: disnake.AppCmdInter, user_input: str) -> list[str]:
    user_input = user_input.lower().strip().replace('/', '').replace(' ', '_')
    if not user_input:
        # EASTER EGG: These are all 5 CHUB admins :3
        return [
            "RagingEnby",
            "TGWaffles",
            "_Foe",
            "Vinush",
            "Bibby"
        ]
    print(f'IGN Autocomplete > [{inter.user.name}]  {user_input}')
    try:
        response = await asyncio.wait_for(
            asyncreqs.get('https://api.ragingenby.dev/stem/' + user_input),
            # timeout so low because 1. people type fast 2. discord is unforgiving asdf
            # with their timeouts on autocomplete
            timeout=3
        )
        if response.status != 200:
            return []
        AUTOCOMPLETE_IGN_CACHE[user_input] = [
            player['name'] for player in await response.json()
        ]
        return AUTOCOMPLETE_IGN_CACHE[user_input]
    except asyncio.TimeoutError:
        print('Timeout error for stem', user_input)
        return []


def ign_param(description: Optional[str]=None) -> commands.Param:  # type: ignore
    return commands.param(
        description=description or "A Minecraft IGN",
        min_length=2, # technically 3, but rarely 2 names exist so why not
        max_length=16,
        autocomplete=autocomplete_ign
    )


def should_scan_museum(game_mode: str, member: dict[str, Any]) -> bool:
    if game_mode != 'normal' and game_mode != 'ironman':
        return False
    if 'museum' not in member.get('player_data', {}).get('visited_zones', []):
        return False
    if member.get('leveling', {}).get('experience', 0.0) < 20:
        return False
    return True
    