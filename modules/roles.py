import config


async def dctr_space_helm(item: dict) -> list[int]:
    roles = [config.SPACE_HELM_ROLE]
    extra_attributes = item['ExtraAttributes']
    if extra_attributes.get('sender_name', '').lower():
        roles.append(config.DCTR_SPACE_HELM_ROLE)
    if 'raffle_year' in extra_attributes:
        roles.append(config.RAFFLE_SPACE_HELM_ROLE)
    return roles


async def check_item(item: dict) -> list[int]:
    roles = []
    match item['ExtraAttributes']['id']:
        case 'DCTR_SPACE_HELM':
            roles.extend(await dctr_space_helm(item))
    return roles


async def get_checker_roles(items: list[dict]) -> list[int]:
    roles = []
    for item in items:
        if not isintance(item, dict):
            continue
        roles.extend(await check_item(item))
    return list(set(roles))  # remove duplicates and then return
