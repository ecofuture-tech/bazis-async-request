from pydantic import BaseModel


class SomeResponseItemSchema(BaseModel):
    some_str: str
    some_int: int
    some_dict: dict
