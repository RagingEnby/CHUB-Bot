import aiohttp

import config


async def get(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop("session", None)
    headers = kwargs.pop("headers", {})
    if session is None or session.closed:
        async with aiohttp.ClientSession() as session:
            return await get(*args, session=session, **kwargs)
    if "api.hypixel.net" in args[0]:
        kwargs["proxy"] = config.PROXY
        kwargs["proxy_auth"] = config.PROXY_AUTH
    try:
        async with session.get(*args, headers=headers, **kwargs) as response:
            await response.read()  # read the response before we __aexit__ so itll store
            if "api.hypixel.net" in response.url.host:
                print(
                    response.status,
                    response.method,
                    str(response.url).split(".net")[-1],
                )
            return response
    except RuntimeError as e:
        if str(e) == "Session is closed":
            return await get(*args, **kwargs)
        raise e


async def post(*args, **kwargs) -> aiohttp.ClientResponse:
    session = kwargs.pop("session", None)
    if session is None:
        async with aiohttp.ClientSession() as session:
            return await post(*args, session=session, **kwargs)
    async with session.get(*args, **kwargs) as response:
        await response.read()
        return response
