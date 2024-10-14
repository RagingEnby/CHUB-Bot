import json
import time
import requests

from scrts import BOT_TOKEN, HYPIXEL_API_KEY

HYPIXEL_GUILD_ID: str = "639d0c668ea8c9185c70caf9"

BOT_DEVELOPER_ID: int = 447861538095759365
BOT_DEVELOPER_MENTION: str = f"<@{BOT_DEVELOPER_ID}>"

STAFF_ROLE: int = 1244837447846592535

VERIFICATION_CHANNEL: int = 1240047359946133624
VERIFICATION_LOG_CHANNEL: int = 1293009280261427330
STAFF_CHANNEL: int = 1183198328045977721
BOT_DEV_CHANNEL: int = 1263673819239809135
LOG_CHANNEL: int = 1264027690332323941

GUILD_ID = 934240413974417439

VERIFIED_ROLE: int = 1240044060102623394
POSSIBLE_SCAMMER_ROLE: int = 935288721199214612
GUILD_MEMBER_ROLE: int = 1249863227014250527

DCTR_SPACE_HELM_ROLE: int = 1134970805810385017
SPACE_HELM_ROLE: int = 1261200854132985967
RAFFLE_SPACE_HELM_ROLE: int = 1261200915109773405

ITEM_ID_ROLES: dict[list[str]|str, int] = {
    "KLOONBOAT": 1217172737160904715, # @Kloonboat
    "ANCIENT_ELEVATOR": 1134970925784256572, # @Ancient Elevator
    "CREATIVE_MIND": 1201988405420888155, # @Creative Mind
    "GAME_BREAKER": 1221149287484887141, # @Gamebreaker
    "POTATO_BASKET": 1261201356073603072, # @Basket of Hope
    "DEAD_BUSH_OF_LOVE": 1245118825746268190, # @Dead Bush of Love*
    "SNOW_SNOWGLOBE": 1221630825830027325, # @Snowglobe
    
    # You must have ALL of these items:
    [
        "MAGIC_CUBE_FLUX",
        "GOLDEN_ANCIENT_EGG_FLUX",
        "PIRATE_BOMB_FLUX",
        "GLISTENING_MELON_FLUX",
        "GOLDEN_APPLE_FLUX",
        "GLOWING_GRAPE_FLUX",
        "MYSTIC_MOON_FLUX",
        "BEACH_BALL_FLUX",
        "CHERRY_BLOSSOM_FLUX",
        "POLAR_LIGHTS_FLUX"
    ]: 1132783153044529283 # @Power Orb Skins
}

RANK_ROLES: dict[str, int] = {
    "YOUTUBER": 935002292791427092, # @Content Creator
    "ADMIN": 1295140666640171018, # @Hypixel Staff
    "GAMEMASTER": 1295140666640171018 # @Hypixel Staff
}

REQUIRES_VERIFICATION: list[int] = [
    VERIFIED_ROLE,
    GUILD_MEMBER_ROLE,
    DCTR_SPACE_HELM_ROLE,
    SPACE_HELM_ROLE,
    RAFFLE_SPACE_HELM_ROLE
]\
    + list(ITEM_ID_ROLES.values())\
    + list(RANK_ROLES.values())

response = None
while response is None or response.status_code != 200:
    print('getting guild data...')
    response = requests.get(f'https://api.hypixel.net/v2/guild?key={HYPIXEL_API_KEY}&id={HYPIXEL_GUILD_ID}')
    if response.status_code != 200:
        print(response.status_code, json.dumps(response.json(), indent=2))
        time.sleep(2)
guild_members: list[str] = [member['uuid'] for member in response.json()['guild']['members']]
