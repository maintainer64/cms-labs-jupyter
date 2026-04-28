from dataclasses import dataclass


@dataclass
class UserInfo:
    user_id: str
    username: str
    email: str
    name: str