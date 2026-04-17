import logging

from tornado import web

from .models import UserInfo
from .rpc import CMSRpcClient
from kubespawner import KubeSpawner
from .utils import setup_logger


class CMSSpawner(KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start working with CMSSpawner')
        self._rpc: CMSRpcClient | None = None

    async def get_rpc_client(self) -> CMSRpcClient:
        if self._rpc is None:
            self._rpc = CMSRpcClient()
        return self._rpc

    async def _start(self):
        if not self.name:
            self.log.warning(f"User {self.user.name} tried to launch a nameless default server.")
            raise web.HTTPError(
                400,
                "Запуск стандартного сервера запрещен. Пожалуйста, используйте ссылки из Moodle для запуска лабораторных работ."
            )
        if self.extra_labels is None:
            self.extra_labels = {}
        if self.user_options and 'profile' in self.user_options:
            attempt_id = str(self.user_options['profile'])
            self.extra_labels.update({
                "hub.jupyter.org/cms_attempt_id": attempt_id,
            })
            self.env['ATTEMPT_ID'] = attempt_id
            self.log.info(f"Updated extra_labels with attempt_id: {attempt_id}")
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

    async def get_user_profile(self, current_spawner: KubeSpawner) -> UserInfo | None:
        if not current_spawner.user:
            self.log.info("Current user is empty")
            return None
        auth_state = await current_spawner.user.get_auth_state()
        if not auth_state:
            self.log.info("Current user state is empty")
            return None
        return UserInfo(
            user_id=auth_state["oauth_user"]["sub"],
            username=auth_state["oauth_user"]["username"],
            email=auth_state["oauth_user"]["email"],
            name=auth_state["oauth_user"]["name"],
        )

    async def profile_list(self, current_spawner: KubeSpawner) -> list | None:
        if not current_spawner.name:
            self.log.warning(f"Attempted to fetch profiles without a specified servername.")
            raise web.HTTPError(
                400,
                "Запуск стандартного сервера запрещен. "
                "Пожалуйста, используйте ссылки из Moodle для запуска лабораторных работ."
            )
        self.log.info("Fetching profiles for user")
        user = await self.get_user_profile(current_spawner)
        if not user:
            return None
        rpc = await self.get_rpc_client()
        attempts = await rpc.list_attempts(
            attempt_ids=[str(current_spawner.name)],
            user_ids=[user.user_id],
            limit=5000,
            offset=0,
        )
        self.log.info(f"Profile list count {len(attempts)} by user {user.username}")
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
