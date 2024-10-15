import aiohttp


async def get(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop('session') if 'session' in kwargs else None
    if session is None:
        # this api request has to be done with no session because of how disnake
        # autocomplete works
        if not args[0].startswith('https://api.ragingenby.dev/stem'):
            print('WARNING: Request to', args[0], 'is being made with no session,'
                  'this will slow the bot down. Ensure this is intentional.')
        async with aiohttp.ClientSession() as session:
            return await get(*args, session=session, **kwargs)

    # this is semi temp. its made to monitor that excessive requests arent being sent
    params = kwargs.get('params', {})
    # wow holy SHIT this print statement is ugly but i cba to make it better
    # also this makes it comply with pRoPEr PrACtiCeS
    print(args[0].split('.net')[-1] + ' - ' +
          params.get('uuid',
            params.get('player',
                params.get('profile'))))
    async with session.get(*args, **kwargs) as response:
        return response
        