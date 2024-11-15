import disnake
import asyncio
from typing import Optional

import motor.motor_asyncio
from pymongo import InsertOne, UpdateOne

import config


class Database:
    def __init__(self, db: str, collection: str):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.client[db]
        self.collection = self.db[collection]
        self.queue: list[UpdateOne|InsertOne] = []
        self.running = False

    async def upload(self):
        queue = self.queue.copy()
        self.queue = []
        if queue:
            await self.collection.bulk_write(queue)

    async def upload_task(self):
        while True:
            if not self.running:
                break
            await self.upload()
            await asyncio.sleep(20)

    async def start(self):
        self.running = True
        asyncio.create_task(self.upload_task())

    async def close(self):
        self.running = False
        if self.queue:
            await self.upload()
        self.client.close()

    async def ensure_started(self):
        if not self.running:
            await self.start()

    async def search(self, query: dict, project: Optional[dict]=None, limit: int|None=50):
        await self.ensure_started()
        cursor = self.collection.find(query, projection=project, limit=limit)
        return await cursor.to_list(length=limit)

    async def add(self, data: dict, force: bool=False):
        await self.ensure_started()
        if force and '_id' in data:
            return await self.collection.update_one(
                {"_id": data['_id']},
                {"$set": data},
                upsert=True
            )
        elif force:
            return await self.collection.insert_one(data)

        if '_id' in data:
            self.queue.append(UpdateOne(
                {"_id": data['_id']},
                {"$set": data},
                upsert=True
            ))
        else:
            self.queue.append(InsertOne(data))


message_db = Database(
    db='Discord',
    collection='messages'
)


async def message_to_dict(message: disnake.Message) -> dict:
    return {
        "_id": message.id,
        "type": message.type,
        "createdAt": message.created_at.timestamp(),
        "editedAt": message.edited_at.timestamp() if message.edited_at else None,
        "pinned": message.pinned,
        "content": message.content,
        "cleanContent": message.clean_content,
        "systemContent": message.system_content,
        "author": message.author.id,
        "bot": author.bot,
        "channel": message.channel.id,
        "category": message.channel.category_id if hasattr(message.channel, 'category_id') else None, # type: ignore
        "guild": message.guild.id if message.guild else None,
        "reference": message.reference.message_id if message.reference else None,
        "system": message.is_system(),
        "embeds": [embed.to_dict() for embed in message.embeds],
        "attachments": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "proxy_url": attachment.proxy_url,
                "url": attachment.url,
                "contentType": attachment.content_type,
                "description": attachment.description,
                "duration": attachment.duration,
                "ephemeral": attachment.ephemeral,
                "height": attachment.height,
                "size": attachment.size,
                "width": attachment.width,
            }
            for attachment in message.attachments
        ],
        "stickers": [
            {
                "id": sticker.id,
                "name": sticker.name,
                "url": sticker.url,
                "format": sticker.format,
            }
            for sticker in message.stickers
        ],
        "reactions": [
            {
                "emoji": str(reaction.emoji),
                "count": reaction.count
            }
            for reaction in message.reactions
        ],
        "userMentions": [user.id for user in message.mentions],
        "roleMentions": [role.id for role in message.role_mentions],
        "channelMentions": [channel.id for channel in message.channel_mentions]
    }


async def log_msg(message: disnake.Message):
    await message_db.add(await message_to_dict(message))
    