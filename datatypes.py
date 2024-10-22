from typing import Literal, Optional
import disnake
from typing_extensions import TypedDict
import json
from uuid import uuid4

TradePaymentType = Literal['Pure Coins', 'Coins + Items', 'Items']


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

    def __str__(self) -> str:
        return self.name

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
        return cls(name=data['name'], uuid=data['id'])


class TradeReportAttachment:
    def __init__(self, url: str, filename: str):
        self.url = url
        self.filename = filename

    @property
    def file(self) -> disnake.File:
        return disnake.File(self.url, filename=self.filename)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "filename": self.filename
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

    @classmethod
    def from_disnake_attachment(cls, attachment: disnake.Attachment):
        return cls(
            url=attachment.url,
            filename=attachment.filename
        )


class TradeReport:
    def __init__(self, author: int, seller: MinecraftPlayer, buyer: MinecraftPlayer, date: str, item: str, price: str, payment_type: TradePaymentType, image: TradeReportAttachment, notes: Optional[str], _id: Optional[str]=None):
        self.id = _id or str(uuid4())
        self.author = author
        self.seller = seller
        self.buyer = buyer
        self.date = date
        self.item = item
        self.price = price
        self.payment_type = payment_type
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
                return disnake.Color.black()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "seller": self.seller.to_dict(),
            "buyer": self.buyer.to_dict(),
            "date": self.date,
            "item": self.item,
            "price": self.price,
            "payment_type": self.payment_type,
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
                f"**Payment Type:** `{self.payment_type}`",
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
            payment_type=data['payment_type'],
            image=TradeReportAttachment.from_dict(data['image']),
            notes=data['notes'],
        )
        