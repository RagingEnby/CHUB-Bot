import asyncio
import time
from typing import Optional

import disnake
import motor.motor_asyncio
from bson import Timestamp
from pymongo import InsertOne, UpdateOne

import config


class Database:
    def __init__(self, db: str, collection: str):
        self.db_name = db
        self.collection_name = collection

        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.client[self.db_name]
        self.collection = self.db[collection]

        self.queue: list[UpdateOne|InsertOne] = []
        self.running = False

    async def restart_client(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.client[self.db_name]
        self.collection = self.db[self.collection_name]

    async def upload(self, queue: Optional[list[UpdateOne|InsertOne]] = None):
        if queue is None:
            queue = self.queue.copy()
            self.queue = []
        if not queue:
            return
        try:
            await self.collection.bulk_write(queue)
        except Exception as e:
            if str(e) == "Cannot use MongoClient after close":
                await self.restart_client()
                return await self.upload(queue)
            raise e
            
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


def message_to_dict(message: disnake.Message, deleted: bool=False) -> dict:
    return {
        "_id": message.id,
        "type": message.type,
        "createdAt": Timestamp(int(message.created_at.timestamp()), 1),
        "editedAt": Timestamp(int(message.edited_at.timestamp()), 1) if message.edited_at else None,
        "deletedAt": Timestamp(int(time.time()), 1) if deleted else None,
        "pinned": message.pinned,
        "content": message.content,
        "deleted": deleted,
        "cleanContent": message.clean_content,
        "systemContent": message.system_content,
        "author": message.author.id,
        "bot": message.author.bot,
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


async def log_msg(message: disnake.Message, deleted: bool=False):
    await message_db.add(message_to_dict(message, deleted=deleted))


async def log_msg_delete(message: disnake.Message|int):
    if isinstance(message, disnake.Message):
        return await log_msg(message, deleted=True)
        
    await message_db.collection.update_one(
        {"_id": message},
        {
            "$set": {
                "deleted": True,
                "deletedAt": Timestamp(int(time.time()), 1),
            }
        }
    )
    