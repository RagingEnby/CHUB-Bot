import aiohttp


async def get(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session')
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await get(*args, session=session, **kwargs)
    async with session.get(*args, **kwargs) as response:
        await response.text()  # wait for response to go through (async can be buggy so this is somewhat needed)
        if response.status == 429 and 'api.hypixel.net' in args[0]:
            print('RATE LIMITED!!!')
            print(json.dumps(response.headers, indent=2))
        return response
        