import logging

from .rpc import CMSRpcClient
from kubespawner import KubeSpawner
from .utils import setup_logger


class CMSSpawner(KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = setup_logger(__name__, logging.ERROR)
        self.logger.info('Start working with CMSSpawner')
        self.rpc: CMSRpcClient | None = None

    async def _start(self):
        self.rpc = CMSRpcClient()
        return await super()._start()

    async def profile_list(self, current_spawner: KubeSpawner) -> list | None:
        if not current_spawner.user:
            current_spawner.log.info("Profile list doesn't exist. User doesn't exist")
            return []
        auth_state = await current_spawner.user.get_auth_state()
        if not auth_state:
            current_spawner.log.info("Profile list doesn't exist. Auth state doesn't exist")
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
        current_spawner.log.info(f"Profile list count {len(attempts)} by user {self.user.username}")
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
