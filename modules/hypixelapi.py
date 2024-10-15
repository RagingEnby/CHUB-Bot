import json
from typing import Optional
import asyncio
import aiohttp

from modules import asyncreqs

import config
import ws

PLAYER_RATE_LIMIT_MSG = "You have already looked up this player too recently, please try again shortly"
API_URL = "https://api.hypixel.net/v2"

LAST_RESPONSE: dict[str, dict] = {}


async def get_data(
        endpoint: str,
        params: Optional[dict] = None,
        session: Optional[aiohttp.ClientSession] = None
) -> aiohttp.ClientResponse:
    if params and 'key' not in params:
        params['key'] = config.HYPIXEL_API_KEY
    url = f"{API_URL}{endpoint}"
    response = await asyncreqs.get(url, params=params, session=session)
    data = await response.json()
    # the queue limit here is because one time the websocket
    # it sends to went offline, and it crashed my
    # server because the queue got so large
    if response.status == 200 and len(ws.queue) <= 1000:
        ws.queue.append({
            "data": data,
            "params": params or {},
            "url": url
        })
    return response


async def ensure_data(endpoint: str,
                      params: Optional[dict] = None,
                      session: Optional[aiohttp.ClientSession] = None) -> dict:
    if 'guild' in endpoint:
        print('ensure_data()')
    global LAST_RESPONSE
    id_ = params.get('uuid', params.get('player', params.get('id', params.get('profile')))) if params else None
    response = await get_data(endpoint, params, session=session)
    if response.status == 200 or response.status == 204:
        data = await response.json()
        if id_:
            LAST_RESPONSE[id_] = data
        return data

    if response.status == 429:
        data = await response.json()
        if data.get('cause') == PLAYER_RATE_LIMIT_MSG:
            if id_ in LAST_RESPONSE:
                return LAST_RESPONSE[id_]
            await asyncio.sleep(35)
            return await ensure_data(endpoint, params, session=session)
        important_headers = {k: v for k, v in dict(response.headers).items() if k.startswith('ratelimit-')}
        print('RATE LIMITED!!!')
        print('important_headers', json.dumps(important_headers, indent=2))
        print('data', json.dumps(data, indent=2))   
    else:
        print(f'received response {response.status} from {endpoint} (params: {json.dumps(params)})')
        
    await asyncio.sleep(5)
    return await ensure_data(endpoint, params, session=session)
    