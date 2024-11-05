import asyncio
import json
import random
from typing import Optional, Any, Literal

import aiofiles
import aiohttp
import disnake
from disnake import user
from disnake.ext import commands
from datetime import datetime

import config
from modules import hypixelapi, parser, usermanager, autocomplete

BOT_CLASS = commands.InteractionBot | commands.Bot | commands.AutoShardedBot


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


async def get_player_items(uuid: str, session: Optional[aiohttp.ClientSession] = None, debug: bool=False) -> tuple[dict[str, dict], list[str]]:
    uuid = uuid.replace('-', '')
    profiles_data = await hypixelapi.ensure_data('/skyblock/profiles', {"uuid": uuid}, session=session)
    if not profiles_data.get('profiles'):
        return {}, []
    if not profiles_data:
        return {}, []
    museum_datas = await asyncio.gather(*[
        hypixelapi.ensure_data('/skyblock/museum', {"profile": profile['profile_id']}, session=session)
        for profile in profiles_data['profiles']
        if should_scan_museum(profile.get('game_mode', 'normal'), profile['members'].get(uuid, {}))
    ])
    inventories = await parser.get_inventories(profiles_data, debug=debug)
    museum_inventories = await parser.get_museum_inventories(profiles=museum_datas)
    items = {}
    applied_items = []
    
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
                if pet.get('skin'):
                    applied_items.append('PET_SKIN_' + pet['skin'])
    for item in items.values():
        skin = item.get('ExtraAttributes', {}).get('skin')
        if skin:
            applied_items.append(skin)
    async with aiofiles.open(f'storage/inv/{uuid}.json', 'w') as file:
        await file.write(json.dumps({"items": items, "applied_items": applied_items}, indent=2))
    return items, applied_items


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
        title="Error: " + title,
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


def ign_param(description: Optional[str]=None) -> commands.Param:  # type: ignore
    return commands.param(
        description=description or "A Minecraft IGN",
        min_length=2, # technically 3, but rarely 2 names exist so why not
        max_length=16,
        autocomplete=autocomplete.ign
    )


def profile_param(description: str, who: Literal['buyer', 'seller']) -> commands.Param:
    return commands.param(
        description=description,
        autocomplete=autocomplete.buyer_profile if who == 'buyer' else autocomplete.seller_profile
    )


def should_scan_museum(game_mode: str, member: dict[str, Any]) -> bool:
    # museum is only available to ironman and standard profiles
    if game_mode not in ['normal', 'ironman']:
        return False

    # you cant have put items in museum if youve never been there
    if 'museum' not in member.get('player_data', {}).get('visited_zones', []):
        return False

    # players with low levels probably havent donated much/anything to museum
    if member.get('leveling', {}).get('experience', 0.0) < 30:
        return False
        
    return True


def uuid_to_user(uuid: str, bot: BOT_CLASS) -> Optional[disnake.User]:
    user_id = usermanager.LinkedUsers.get(uuid)
    if user_id is None:
        return None
    return bot.get_user(user_id)


def parse_date(date: str) -> Optional[datetime]:
    # expected date format:
    # MM/DD/YYYY HH:MM AM/PM
    # 11/5/2024 12:25 PM
    try:
        parsed_date = datetime.strptime(date, "%m/%d/%Y %I:%M %p")
        current_time = datetime.now()
        if parsed_date < current_time:
            return parsed_date
        return None
    except ValueError:
        return None


def get_date() -> str:
    return datetime.now().strftime("%m/%d/%Y %I:%M %p")
