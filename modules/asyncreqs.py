import aiohttp

import config


async def get(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session', None)
    headers = kwargs.pop('headers', {})
    headers['User-Agent'] = config.USER_AGENT
    if session is None or session.closed:
        async with aiohttp.ClientSession() as session:
            return await get(*args, session=session, **kwargs)
    try:
        async with session.get(*args, headers=headers, **kwargs) as response:
            await response.read() # read the response before we __aexit__ so itll store
            return response
    except RuntimeError as e:
        if str(e) == "Session is closed":
            return await get(*args, **kwargs)
        raise e


async def post(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session', None)
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await post(*args, session=session, **kwargs)
    async with session.get(*args, **kwargs) as response:
        await response.read()
        return response
        