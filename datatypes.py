import json
from typing import Optional
from uuid import uuid4

import disnake
from typing_extensions import TypedDict


class MinecraftPlayerDict(TypedDict):
    id: str
    name: str
    

class InvalidPlayerDictError(ValueError):
    def __init__(self, message, provided_dict: dict | None):
        super().__init__(message)
        self.provided_dict = provided_dict

    def dict_as_str(self):
        if self.provided_dict is None:
            return "<No dictionary provided>"
        return json.dumps(self.provided_dict, indent=2)


class MinecraftPlayer:
    def __init__(self, name: str, uuid: str):
        self.name = name
        self.uuid = uuid

    @property
    def id(self) -> str:
        return self.uuid

    @property
    def avatar(self) -> str:
        return "https://mc-heads.net/avatar/" + self.uuid

    def __str__(self) -> str:
        return f"{self.name} ({self.uuid})"

    def to_dict(self) -> MinecraftPlayerDict:
        return {
            "id": self.uuid,
            "name": self.name
        }

    @classmethod
    def from_dict(cls, data: MinecraftPlayerDict):
        if not data.get('id') or not data.get('name'):
            print('invalid player data:', json.dumps(data, indent=2))
            return None
        return cls(name=data['name'], uuid=data.get('id', data.get('uuid')))


class TradeReportAttachment:
    def __init__(self, url: str, filename: str):
        self.url = url
        self.filename = filename

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "filename": self.filename
        }

    @classmethod
    def from_dict(cls, data: dict):
        if 'name' in data:
            data['filename'] = data.pop('name')
        return cls(**data)

    @classmethod
    def from_disnake_attachment(cls, attachment: disnake.Attachment):
        return cls(
            url=attachment.url,
            filename=attachment.filename
        )


class TradeReport:
    def __init__(self, author: int, seller: MinecraftPlayer, buyer: MinecraftPlayer, date: str, item: str, price: str, image: TradeReportAttachment, notes: Optional[str], _id: Optional[str]=None):
        self.id = _id or str(uuid4())
        self.author = author
        self.seller = seller
        self.buyer = buyer
        self.date = date
        self.item = item
        self.price = price
        self.image = image
        self.notes = notes

    def color(self, status: str="pending") -> disnake.Color:
        match status:
            case "pending":
                return disnake.Color.yellow()
            case "accepted":
                return disnake.Color.green()
            case "denied":
                return disnake.Color.red()
            case _:
                return disnake.Color.dark_gray()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "seller": self.seller.to_dict(),
            "buyer": self.buyer.to_dict(),
            "date": self.date,
            "item": self.item,
            "price": self.price,
            "image": self.image.to_dict(),
            "notes": self.notes,
        }

    def to_embed(self, status: str="pending") -> disnake.Embed:
        embed = disnake.Embed(
            title=f"Trade Report ({status.upper()})",
            color=self.color(status),
            description='\n'.join([
                f"**Author:** <@{self.author}>",
                f"**Seller:** `{self.seller}`",
                f"**Buyer:** `{self.buyer}`",
                f"**Date:** `{self.date}`",
                f"**Item:** `{self.item}`",
                f"**Price:** `{self.price}`",
                f"**Notes:** `{self.notes}`"
            ])
        )
        embed.set_image(url=self.image.url)
        return embed

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get('id'),
            author=data['author'],
            seller=MinecraftPlayer.from_dict(data['seller']), # type: ignore
            buyer=MinecraftPlayer.from_dict(data['buyer']), # type: ignore
            date=data['date'],
            item=data['item'],
            price=data['price'],
            image=TradeReportAttachment.from_dict(data['image']),
            notes=data['notes'],
        )
        