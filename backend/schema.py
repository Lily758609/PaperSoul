from pydantic import BaseModel
from typing import List

class CharacterCard(BaseModel):
    id: str
    display_name: str
    book_title: str
    book_id:str
    identity:List[str]
    appearence:List[str]
    personal: List[str]
    speech_style: List[str]
    relationships: List[str]
    interaction_with_xiaoyao: List[str]
    principles: List[str]
    world_rules: List[str]
    safety_rules: List[str]
    interaction_with_xiaoyao: List[str]

