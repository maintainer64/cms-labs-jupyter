import asyncio
import logging

import yaml
from kubernetes_asyncio import utils, client
from kubernetes_asyncio.client import ApiException
from kubespawner import KubeSpawner
from tornado import web

from cmsspawner.cms_client.rpc import CMSRpcClient
from cmsspawner.git_client.client import GitClient
from .models import UserInfo
from .utils import setup_logger


class CMSSpawner(KubeSpawner):
    """
    Класс хранит базовую логику для списка профилей и создание информации в кубернетес
    """
    git_url: str = ""
    git_branch: str = "master"

    extra_pod_config = {
        "restartPolicy": "Always",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start working with CMSSpawner')

    async def _start(self):
        """
        Внутренний метод спавнера, который аллоцирует появление ресурсов
        :return: После выхода из этого метода появляются артефакты в виде диска, сервера и пода (иногда неймспейса)
        """
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

    async def _ensure_namespace(self):
        await super()._ensure_namespace()
        if not self.user_options.get('profile'):
            self.log.info(f"User not used profile with attempts")
            return None
        attempt_id = str(self.user_options['profile'])
        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            attempt_ids=[attempt_id],
            limit=1,
            offset=0,
        )
        if not attempts:
            self.log.info(f"User not found running attempt with CMS")
            return None
        attempt = attempts[0]
        labs_path = attempt.get('labs_path')
        if not labs_path:
            self.log.info(f"User spawned labs without task")
            return None
        git_client = GitClient()
        topology = await git_client.get_topology_file(labs_path=labs_path)
        self.log.info(f"Topology file found. Start deploy")
        topology = topology.replace("$NAME", self.namespace)
        await self._apply_manifests(yaml_content=topology)
        return None

    async def _apply_manifests(self, yaml_content: str):
        """Применяет Kubernetes манифесты из YAML (аналог kubectl apply -f)
        Поддерживает как стандартные ресурсы, так и CRD (Containerlab).
        """
        # Загружаем все манифесты и убираем пустые блоки (None)
        manifests = [m for m in yaml.safe_load_all(yaml_content) if m]
        total = len(manifests)
        kind = ""

        for idx, manifest in enumerate(manifests, start=1):
            try:
                # 1. Подготовка метаданных
                kind = manifest.get('kind', "")
                api_version = manifest.get('apiVersion', '')

                if 'metadata' not in manifest:
                    manifest['metadata'] = {}
                if 'namespace' not in manifest['metadata']:
                    manifest['metadata']['namespace'] = self.namespace

                self.log.info(f"Topology file applying... {idx}/{total} [{kind}]")

                # 2. Определяем параметры для API
                # Разделяем apiVersion на group и version (например, 'apps/v1' или 'v1')
                if '/' in api_version:
                    group, version = api_version.split('/')
                else:
                    group, version = "", api_version

                # Для CustomObjectsApi нужно plural имя (обычно это kind во множественном числе)
                # Для Containerlab -> containerlabs, Deployment -> deployments
                plural = kind.lower() + "s"

                # 3. Выполняем запрос через универсальный CustomObjectsApi
                custom_api = client.CustomObjectsApi(api_client=self.api)

                await asyncio.wait_for(
                    custom_api.create_namespaced_custom_object(
                        group=group,
                        version=version,
                        namespace=self.namespace,
                        plural=plural,
                        body=manifest
                    ),
                    timeout=self.k8s_api_request_timeout,
                )

            except ApiException as e:
                if e.status == 409:
                    self.log.info(f"Resource {kind} already exists, skipping...")
                else:
                    self.log.exception(f"Failed to create topology resource {kind} in {self.namespace}")
                    raise
            except Exception:
                self.log.exception(f"Unexpected error applying manifest {idx}")
                raise
            self.log.info(f"Topology file apply {idx}/{total} done")

    async def get_options_form(self):
        """
        Метод отдаёт список запущенных попыток у пользователя
        (перегружен, чтобы не использовать дефолтные параметры)
        :return: Список профилей пользователя в формате HTML
        """
        profiles = await self.profile_list(self)
        if not profiles:
            self.log.warning(f"User tried to login but has no active attempts.")
            raise web.HTTPError(
                403,
                "У вас нет активных сессий в Moodle для запуска сервера."
            )
        return await super().get_options_form()

    async def get_user_profile(self, current_spawner: KubeSpawner) -> UserInfo | None:
        """
        Метод получает из текущий профиль пользователя
        :param current_spawner: Текущий спавнер под блокнота
        :return: Профиль пользователя или None
        """
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
        """
        Функция которая внутри KubeSpawner вызывается автоматически (не перегружена) для списка профилей
        :param current_spawner: Текущий spawner
        :return: Возвращает попытки лабораторной у пользователя не завершенные
        """
        self.log.info("Fetching profiles for user")
        profile = await self.get_user_profile(current_spawner)
        if not profile:
            return None
        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            user_ids=[profile.user_id],
            statuses=["pending", "active"],
            limit=5000,
            offset=0,
        )
        self.log.info(f"Profile list count {len(attempts)} by user {profile.username}")
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
