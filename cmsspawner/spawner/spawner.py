import logging

from tornado import web

from .rpc import CMSRpcClient
from kubespawner import KubeSpawner
from .utils import setup_logger


class CMSSpawner(KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start working with CMSSpawner')
        self.rpc: CMSRpcClient | None = None

    async def _start(self):
        self.rpc = CMSRpcClient()
        return await super()._start()

    async def get_options_form(self):
        profiles = await self.profile_list(self)
        try:
            user_name = self.user.name
        except Exception:
            user_name = None
        if not profiles:
            self.log.warning(f"User {user_name} tried to login but has no active attempts.")
            raise web.HTTPError(
                403,
                "У вас нет активных сессий в Moodle для запуска сервера."
            )
        return await super().get_options_form()

    async def profile_list(self, current_spawner: KubeSpawner) -> list | None:
        self.log.info("Fetching profiles for user")
        if not current_spawner.user:
            self.log.info("Profile list doesn't exist. User doesn't exist")
            return []
        auth_state = await current_spawner.user.get_auth_state()
        if not auth_state:
            self.log.info("Profile list doesn't exist. Auth state doesn't exist")
            return []
        try:
            print("auth_state", auth_state)
        except Exception:
            pass
        try:
            print("self.user", current_spawner.user.id)
        except Exception:
            pass
        try:
            print("self.user.email", current_spawner.user.email)
        except Exception:
            pass
        attempts = await self.rpc.list_attempts(
            user_ids=[],
            statuses=["pending"],
            limit=5000,
            offset=0,
        )
        self.log.info(f"Profile list count {len(attempts)} by user {self.user.username}")
        profiles = []
        for attempt in attempts:
            attempt_id = attempt['attempt_id']
            attempt_number = attempt['id']
            display_name = attempt.get('lti_routing_name') or attempt.get("user_name") or f"Attempt {attempt_id}"
            description = f"Элемент курса совершён с номером попытки attempt_id({attempt_number})"
            profile = {
                'slug': attempt_id,
                'display_name': display_name,
                'default': False,
                'description': description,
            }
            profiles.append(profile)
        return profiles
