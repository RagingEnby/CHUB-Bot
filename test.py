import aiofiles
import asyncio
import json

from modules import parser

with open('data.json', 'r') as file:
    data = json.load(file)


async def main():
    items = await parser.get_inventories(data)
    async with aiofiles.open('parsed.json', 'w') as file:
        await file.write(json.dumps(items, indent=2))

asyncio.run(main())