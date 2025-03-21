import asyncio
import base64
import io
import json
from typing import Optional

import aiofiles
from nbt import nbt


async def nbt_to_dict(nbt_data) -> dict:
    if isinstance(nbt_data, nbt.NBTFile) or isinstance(nbt_data, nbt.TAG_Compound):
        return {tag.name: await nbt_to_dict(tag) for tag in nbt_data.tags}
    elif isinstance(nbt_data, nbt.TAG_List):
        return [await nbt_to_dict(item) for item in nbt_data.tags]
    elif isinstance(nbt_data, nbt.TAG_Byte_Array) or isinstance(nbt_data, nbt.TAG_Int_Array):
        return nbt_data.value
    elif isinstance(nbt_data, nbt.TAG_String):
        return nbt_data.value
    else:
        return nbt_data.value


async def un_gzip(gzipped_data: bytes) -> dict:
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: nbt.NBTFile(fileobj=io.BytesIO(gzipped_data)))
    return await nbt_to_dict(data)


async def decode_bytes(item_bytes: str = None, gzipped_data=None) -> list[dict]:
    if item_bytes is None and gzipped_data is None:
        raise ValueError("Either item_bytes or gzipped_data must be provided")

    if not gzipped_data:
        gzipped_data = base64.b64decode(item_bytes)
    dict_data = await un_gzip(gzipped_data)
    data = await ensure_all_decoded(dict_data)
    formatted_data = []
    if 'i' in data and len(data) == 1:
        data = data['i']
        for item in data:
            if 'tag' not in item:
                continue
            tag = item['tag']
            tag['Damage'] = item['Damage']
            formatted_data.append(tag)

    elif len(data) > 1:
        print('len(data) > 1')
        print(json.dumps(data, indent=2))
    return formatted_data


async def ensure_all_decoded(data: dict) -> dict:
    for k, v in data.items():
        if isinstance(v, dict):
            data[k] = await ensure_all_decoded(v)
        elif isinstance(v, list):
            data[k] = await asyncio.gather(*[
                ensure_all_decoded(item) for item in v
                if isinstance(item, (dict, list))
            ])
        elif isinstance(v, bytearray):
            # TODO: Fix this (this does not work)
            decoded_v = await decode_bytes(gzipped_data=v)
            if len(decoded_v) == 1 and 'i' in decoded_v[0]:
                decoded_v = decoded_v[0]['i']
            data[k] = decoded_v
    return data


async def decode_item(item_bytes: str) -> dict:
    dict_data = await decode_bytes(item_bytes)
    print('decode_bytes() ->', type(dict_data))
    if len(dict_data) == 1:
        return await ensure_all_decoded(dict_data[0])
    raise ValueError("unexpected item data format: " + str(dict_data))


async def decode_items(item_bytes: str) -> list[dict]:
    data: list[dict] = await decode_bytes(item_bytes)
    return await asyncio.gather(*[ensure_all_decoded(item) for item in data])


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
            formatted_member_data['parsed'] = await asyncio.gather(*[
                decode_items(item_bytes)
                for item_bytes in formatted_member_data['bytes']
            ])
            remove = []
            for i, item_data in enumerate(formatted_member_data['parsed']):
                if isinstance(item_data, list):
                    remove.append(i)
                    for item in item_data:
                        formatted_member_data['parsed'].append(item)
            for i in reversed(remove):
                del formatted_member_data['parsed'][i]
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
            parsed = {inv_name: await decode_bytes(inv_contents) for inv_name, inv_contents in inventories.items() if isinstance(inv_contents, str)}
            items.append({
                "playerId": uuid,
                "profileId": profile['profile_id'],
                "parsed": parsed
            })
    return items
