import asyncio
import websockets
import json
import lz4.frame
import msgpack
import constants
from asyncio import Queue


queue = Queue(maxsize=1000)
uri = "wss://api.ragingenby.dev/hypixeltracking/ws"


def send(data):
    if not queue.full():
        queue.put_nowait(data)


async def websocket_connector():
    global queue
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps({
                    "method": "login",
                    "content": "ChubBot",
                    "compression": "lz4.msgpack"
                }))
                print('logged into ws')

                while constants.ALIVE:
                    msg = []
                    while len(msg) < 25:
                        msg.append(await queue.get())
                    await websocket.send(lz4.frame.compress(msgpack.packb(msg)))

        except Exception as e:
            print(f'<!> ws error: {e}')
        finally:
            await asyncio.sleep(10)


async def start():
    asyncio.create_task(websocket_connector())
