import asyncio
import json
import random
from datetime import datetime
from typing import Any, Literal, Optional
import time

import aiofiles
import aiohttp
import disnake
from disnake.ext import commands

import config
import datatypes
from modules import asyncreqs, autocomplete, hypixelapi, parser, usermanager

Bot = commands.InteractionBot | commands.Bot | commands.AutoShardedBot


async def get_user_from_name(bot: Bot, name: str) -> Optional[disnake.Member]:
    for member in bot.get_guild(config.GUILD_ID).members: # type: ignore
        if member.name == name:
            return member
    return None


def get_guild(bot: Bot) -> disnake.Guild:
    return bot.get_guild(config.GUILD_ID) # type: ignore


async def get_members(bot: Bot) -> list[disnake.Member]:
    return get_guild(bot).members


async def get_member(bot: Bot, user_id: int) -> Optional[disnake.Member]:
    return get_guild(bot).get_member(user_id)


async def get_member_dict(bot: Bot) -> dict[int, disnake.Member]:
    return {member.id: member for member in await get_members(bot)}


async def get_role(bot: Bot, role_id: int) -> Optional[disnake.Role]:
    return get_guild(bot).get_role(role_id)


async def ban_member(bot: Bot, user_id: int, reason: Optional[str] = None):
    await get_guild(bot).ban(disnake.Object(user_id), reason=reason)


async def get_player_items(uuid: str, session: Optional[aiohttp.ClientSession] = None) -> tuple[dict[str, dict], list[str]]:
    uuid = uuid.replace('-', '')
    profiles_data = await hypixelapi.ensure_data('/skyblock/profiles', {"uuid":  uuid}, session=session)
    if not profiles_data.get('profiles'):
        return {}, []
    if not profiles_data:
        return {}, []
    museum_datas = await asyncio.gather(*[
        hypixelapi.ensure_data('/skyblock/museum', {"profile": profile['profile_id']}, session=session)
        for profile in profiles_data['profiles']
        if should_scan_museum(profile.get('game_mode', 'normal'), profile['members'].get(uuid, {}))
    ])
    inventories = await parser.get_inventories(profiles_data)
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


def randomize_dict_order(input_dict: dict) -> dict:
    keys = list(input_dict.keys())
    random.shuffle(keys)
    return {key: input_dict[key] for key in keys}


async def get_guild_members(session: Optional[aiohttp.ClientSession] = None) -> list[str]:
    data = await hypixelapi.ensure_data("/guild", {"id": config.HYPIXEL_GUILD_ID}, session=session)
    return [member['uuid'] for member in data['guild']['members']]


def make_cmd_str(inter: disnake.AppCmdInter) -> str:
    log_params = " ".join([f"{name}:{value}" for name, value in inter.filled_options.items()])
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
    if not inter.author.get_role(config.STAFF_ROLE): # type: ignore
        await inter.send(embed=make_error(
            "no permissions",
            f"You must have the <@&{config.STAFF_ROLE}> role to use this command!"
        ))
        return False
    if role and inter.author.top_role <= role: # type: ignore
        await inter.send(embed=make_error(
            "not allowed",
            f"You are not allowed to give away this role as it is above your top role "
            f"({inter.author.top_role.mention})"
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


def profile_param(description: str, who: Literal['buyer', 'seller']) -> commands.Param: # type: ignore
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


def uuid_to_user(uuid: str, bot: Bot) -> Optional[disnake.User]:
    user_id = usermanager.linked_users.get(uuid)
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


async def make_backgroundcheck_embed(player: datatypes.MinecraftPlayer, member: Optional[disnake.Member]=None, session: Optional[aiohttp.ClientSession]=None) -> tuple[disnake.Embed, str]:
    response = await asyncreqs.get(f'https://api.ragingenby.dev/backgroundcheck/{player.uuid}', session=session)
    data = await response.json()
    description = [
        f"**Linked To:** {member.mention}" if member else "",
        f"**Discord Created:** <t:{int(member.created_at.timestamp())}:R>" if member else "",
        f"**Joined Server:** <t:{int(member.joined_at.timestamp())}:R>",
        f"**First Hypixel Login:** <t:{round(data['firstLogin'])//1000}:R>" if data['firstLogin'] else "",
        f"**Possible Alts:** `{', '.join([disnake.utils.escape_markdown(player['name']) for player in data['possibleAlts']]) if data['possibleAlts'] else 'None'}`"
    ]
    embed = disnake.Embed(
        description='\n'.join(description)
    )
    embed.set_author(
        name=data['rankname'] or player.name,
        icon_url=player.avatar
    )
    if member:
        embed.set_footer(
            text=f"{member.name} ({member.id})",
            icon_url=member.display_avatar.url
        )
    max_nw = 0
    max_nw_api_enabled = False
    if data['skyblockProfiles']:
        for profile in data['skyblockProfiles']:
            if profile['networth'] > max_nw:
                max_nw = profile['networth']
                max_nw_api_enabled = not any(profile['disabled'].values())
            value = [
                f"Selected: {':white_check_mark:' if profile['selected'] else ':x:'}",
                f"Profile Type: `{profile['game_mode']}`",
                f"Networth: `{numerize(profile['networth'])}`",
                f"Level: `{profile['sbLevel']}`",
                f"Fairy Souls: `{profile['fairySouls']}`",
            ]
            for weight_name, weight_value in profile['weight'].items():
                value.append(f"-# {weight_name.title()} Weight: `{round(weight_value, 2)}`")
            embed.add_field(
                name=profile['cute_name'],
                value='\n'.join(value)
            )
    else:
        embed.add_field(
            name="No Profiles",
            value="No SkyBlock profiles found"
        )
    max_fairy_souls = max([profile['fairySouls'] for profile in data['skyblockProfiles']])
    banned_coop = any(
        usermanager.banned_users.get(uuid)
        for uuid in data['coopMembers']
    )
    content = ""
    # if inter.author.created_at is less than 6 months ago
    if any([
        member and time.time() - member.created_at.timestamp() < 2592000,
        max_fairy_souls < 100,
        max_nw < 3_000_000_000 and max_nw_api_enabled,
        banned_coop
    ]):
        content = config.SUS_ACCOUNT_PING
    return embed, content
