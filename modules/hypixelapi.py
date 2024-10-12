import json
from typing import Optional
import asyncio
import aiohttp

from modules import asyncreqs

import config
import ws

API_URL = "https://api.hypixel.net/v2"


async def get_data(
        endpoint: str,
        params: Optional[dict] = None,
        session: Optional[aiohttp.ClientSession] = None
) -> aiohttp.ClientResponse:
    if params and 'key' not in params:
        params['key'] = config.HYPIXEL_API_KEY
    url = f"{API_URL}{endpoint}"
    response = await asyncreqs.get(url, params=params, session=session)
    if response.status == 200:
        ws.queue.append({
            "data": await response.json(),
            "params": params or {},
            "url": url
        })
    return response


async def ensure_data(endpoint: str,
                      params: Optional[dict] = None,
                      session: Optional[aiohttp.ClientSession] = None) -> dict:
    response = await get_data(endpoint, params, session=session)
    if response.status not in [200, 204]:
        if response.status != 429:
            print(
                f'received response {response.status} from {endpoint} (params: {json.dumps(params)})'
            )
        await asyncio.sleep(5)
        return await ensure_data(endpoint, params, session=session)
    return await response.json()
