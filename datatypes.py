from typing_extensions import TypedDict
import json


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

