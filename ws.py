# if you're just a random person you can ignore this file
# the point of this is i keep a mongodb database with requests
# made by any of my bots/services. this is just to communicate
# with the central program that controls this.

import asyncio
import json
from asyncio import CancelledError, TimeoutError

import websockets
from websockets import ConnectionClosedError, InvalidStatusCode

queue = []


async def websocket_connector():
    global queue
    try:
        async with websockets.connect("wss://api.ragingenby.dev/hypixeltracking/ws") as websocket:
            print('ws connected')
            await websocket.send(json.dumps({"method": "login", "content": "ChubBot"}))
            while True:
                if not queue:
                    await asyncio.sleep(0.2)
                    continue
                await websocket.send(json.dumps(queue.pop(0)))
    except (ConnectionClosedError, InvalidStatusCode, CancelledError, TimeoutError) as e:
        print('ws disconnected:', e)
        await asyncio.sleep(3)
        await websocket_connector()

    except KeyboardInterrupt:
        return
    
    except Exception as e:
        if 'Connect call failed' not in str(e):
           print('unknown ws error:', e)
        await asyncio.sleep(3)
        await websocket_connector()


async def start():
    asyncio.create_task(websocket_connector())
