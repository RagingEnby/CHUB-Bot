import json
import base64
from nbt import nbt
import io
import asyncio


async def nbt_to_dict(nbt_data):
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
            data[k] = [await ensure_all_decoded(item) for item in v if isinstance(item, dict) or isinstance(item, list)]
        elif isinstance(v, bytearray):
            # TODO: Fix this (this does not work)
            decoded_v = await decode_bytes(gzipped_data=v)
            if len(decoded_v) == 1 and 'i' in decoded_v[0]:
                decoded_v = decoded_v[0]['i']
            data[k] = decoded_v
    return data


async def decode_item(item_bytes: str) -> dict:
    # TODO: Fix this (this does not work for the same reason)
    dict_data = await decode_bytes(item_bytes)
    if len(dict_data) == 1 and 'i' in dict_data[0]:
        data = await ensure_all_decoded(dict_data[0]['i'])
        return data
    raise ValueError("unexpected item data format: " + str(dict_data))


async def get_inventories(sb_data: dict) -> list[dict]:
    items = []
    for profile in sb_data['profiles']:
        for uuid, member_data in profile['members'].items():
            inventories = {
                inv_name: inv_data['data'] for inv_name, inv_data in member_data.get('inventory', {}).items()
                if isinstance(inv_data, dict) and 'data' in inv_data
            }
            rift_inventory = member_data.get('rift', {}).get('inventory', {})
            inventories.update(
                {
                    "rift_" + inv_name: inv_data['data'] for inv_name, inv_data in rift_inventory.items()
                    if isinstance(inv_data, dict) and 'data' in inv_data
                }
            )
            parsed = {inv_name: await decode_bytes(inv_contents) for inv_name, inv_contents in inventories.items()}
            items.append({
                "playerId": uuid,
                "profileId": profile['profile_id'],
                "parsed": parsed
            })
    return items
