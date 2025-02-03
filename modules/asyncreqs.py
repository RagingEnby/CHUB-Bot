import aiohttp


async def get(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session', None)
    if session is None or session.closed:
        # this api request has to be done with no session because of how disnake
        # autocomplete works
        #if not args[0].startswith('https://api.ragingenby.dev/stem'):
        #    print('WARNING: Request to', args[0], 'is being made with no session,'
        #          'this will slow the bot down. Ensure this is intentional.')
        async with aiohttp.ClientSession() as session:
            return await get(*args, session=session, **kwargs)
    try:
        async with session.get(*args, **kwargs) as response:
            await response.read() # wait for response (async is buggy)
            return response
    except RuntimeError as e:
        if str(e) == "Session is closed":
            async with aiohttp.ClientSession() as session:
                return await get(*args, session=session, **kwargs)
        raise e


async def post(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session', None)
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await post(*args, session=session, **kwargs)
    async with session.get(*args, **kwargs) as response:
        await response.read()
        return response
        