from dataclasses import dataclass


@dataclass
class UserInfo:
    user_id: str
    username: str = auth_state["oauth_user"]["username"]
    email: str = auth_state["oauth_user"]["email"]
    name: str = auth_state["oauth_user"]["name"]