import aiofiles
import json
import asyncio


class DictManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            with open(file_path, 'r') as file:
                self.data = json.load(file)
        except FileNotFoundError:
            self.data = {}

    async def save(self):
        async with aiofiles.open(self.file_path, 'w') as file:
            await file.write(json.dumps(self.data))

    def save_noasync(self):
        with open(self.file_path, 'w') as file:
            json.dump(self.data, file)

    async def update(self):
        async with aiofiles.open(self.file_path, 'r') as file:
            self.data = json.loads(await file.read())

    def values(self):
        return self.data.values()

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __iter__(self):
        return self.data.__iter__()

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]
        self.save_noasync()


class ListManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            self.data = json.load(open(file_path, 'r'))
        except FileNotFoundError:
            self.data = []

    async def save(self):
        async with aiofiles.open(self.file_path, 'w') as file:
            await file.write(json.dumps(self.data))

    async def update(self):
        async with aiofiles.open(self.file_path, 'r') as file:
            self.data = json.loads(await file.read())

    def __iter__(self):
        return self.data.__iter__()

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]
