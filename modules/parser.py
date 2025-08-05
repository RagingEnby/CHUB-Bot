import io
import json
from base64 import b64decode
from contextlib import suppress
from typing import Any, Optional

from nbt import nbt


def nbt_to_dict_(nbt_data: nbt.NBTFile|nbt.TAG_Compound|nbt.TAG_List|Any) -> dict|list|Any:
    if isinstance(nbt_data, (nbt.NBTFile, nbt.TAG_Compound)):
        return {tag.name: nbt_to_dict_(tag) for tag in nbt_data.tags}
    elif isinstance(nbt_data, nbt.TAG_List):
        return [nbt_to_dict_(item) for item in nbt_data.tags]
    return nbt_data.value


def nbt_to_dict(nbt_data: nbt.NBTFile) -> list[dict]:
    # The ONLY point of this function is to make sure IDEs know the
    # proper datatype returned when passing a single object
    return nbt_to_dict_(nbt_data)  # type: ignore [assignment]


def raw_decode(data: bytes) -> list[dict[str, Any]]:
    with io.BytesIO(data) as fileobj:
        parsed_data: dict[str, list[dict[str, Any]]] = nbt_to_dict(nbt.NBTFile(fileobj=fileobj)) # type: ignore [assignment]
        if len(parsed_data) == 1 and 'i' in parsed_data:
            return parsed_data['i']
        else:
            raise ValueError('Invalid item data', data)


def ensure_all_decoded(data: dict[str, Any]|Any) -> dict[str, Any]:
    for k, v in data.items():
        if k == 'petInfo' and isinstance(v, str):
            with suppress(json.JSONDecodeError):
                data[k] = json.loads(v)
        if isinstance(v, dict):
            data[k] = ensure_all_decoded(v)
        elif isinstance(v, list):
            data[k] = [
                ensure_all_decoded(item)
                if isinstance(item, (dict, list))
                else item for item in v
            ]
        elif isinstance(v, bytearray):
            data[k] = str(v)
            #data[k] = raw_decode(v)
    return data



def decode(item_bytes: str) -> list[dict[str, Any]]:
    return [ensure_all_decoded(i) for i in raw_decode(b64decode(item_bytes))]


def decode_single(item_bytes: str) -> dict[str, Any]:
    return decode(item_bytes)[0]


async def get_museum_inventories(profiles: list[dict]) -> list[dict]:
    members_data = []
    for profile in profiles:
        # allow for passing just the data, or the entire response:
        if 'profile' in profile:
            profile = profile['profile']
            
        for member_uuid, member_data in profile['members'].items():
            formatted_member_data = {
                "playerId": member_uuid,
                "bytes": []
            }
            for item_data in member_data.get('items', {}).values():
                item_bytes = item_data.get('items', {}).get('data')
                if item_bytes is None:
                    continue
                formatted_member_data['bytes'].append(item_bytes)
            for item_data in member_data.get('special', []):
                item_bytes = item_data.get('items', {}).get('data')
                if item_bytes is None:
                    continue
                formatted_member_data['bytes'].append(item_bytes)
            formatted_member_data['parsed'] = []
            for item_bytes in formatted_member_data['bytes']:
                decoded_items = decode(item_bytes)
                formatted_member_data['parsed'].extend(decoded_items)

            del formatted_member_data['bytes']
            members_data.append(formatted_member_data)
    return members_data


def process_inventory(data: dict[str, int|str|dict], parent: Optional[str]=None) -> dict[str, dict]:
    parent = parent + '_' if parent else ''
    inventories = {}
    for inv_name, inv_data in data.items():
        if not isinstance(inv_data, dict):
            continue
        if 'data' in inv_data:
            inventories[parent + inv_name] = inv_data['data']
            continue
        for sub_inv_name, sub_inv_data in inv_data.items():
            if isinstance(sub_inv_data, dict) and 'data' in sub_inv_data:
                inventories[parent + f"{inv_name}_{sub_inv_name}"] = sub_inv_data['data']
    return inventories
    

async def get_inventories(sb_data: dict) -> list[dict]:
    items = []
    for profile in sb_data['profiles']:
        for uuid, member_data in profile['members'].items():
            inventories = process_inventory(member_data.get('inventory', {}))
            inventories.update(process_inventory(member_data.get('rift', {}).get('inventory', {}), parent='rift'))
            inventories.update(process_inventory(member_data.get('shared_inventory', {}), parent='shared_inventory'))
            # combine all the inventory dicts:
            parsed = {}
            for inv_name, inv_contents in inventories.items():
                try:
                    parsed[inv_name] = decode(inv_contents)
                except UnicodeDecodeError as e:
                    print('unable to parse inventory data for', uuid, profile['profile_id'], inv_name, e, sep=' - ')
                    continue
            items.append({
                "playerId": uuid,
                "profileId": profile['profile_id'],
                "parsed": parsed
            })
    return items
