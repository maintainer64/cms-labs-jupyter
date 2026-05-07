from jupyterhub.handlers import BaseHandler
from kubespawner.clients import shared_client, load_config
from tornado import web

from cmsspawner.cms_client.rpc import CMSRpcClient
from cmsspawner.git_client.client import GitClient
from cmsspawner.spawner.kubectl_topology import KubectlTopology
from cmsspawner.spawner.models import UserInfo
from cmsspawner.spawner.spawner import CMSSpawner


class TopologyHandler(BaseHandler):
    route = r"/containerlab/topology/create"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_config(
            host=CMSSpawner.k8s_api_host,
            ssl_ca_cert=CMSSpawner.k8s_api_ssl_ca_cert,
            verify_ssl=CMSSpawner.k8s_api_verify_ssl,
        )
        self.core_api = shared_client("CoreV1Api")

    async def get_user_profile(self) -> UserInfo | None:
        """
        Получает профиль текущего пользователя из данных токена CMS
        """
        user = await self.get_current_user()
        if not user:
            self.log.info("Current user is empty")
            return None

        auth_state = await user.get_auth_state()
        if not auth_state:
            self.log.info("Current user state is empty")
            return None

        return UserInfo(
            user_id=auth_state["oauth_user"]["sub"],
            username=auth_state["oauth_user"]["username"],
            email=auth_state["oauth_user"]["email"],
            name=auth_state["oauth_user"]["name"],
        )

    @web.authenticated
    async def post(self, *args, **kwargs):
        # Получаем профиль пользователя
        profile = await self.get_user_profile()
        if not profile:
            self.set_status(400)
            return self.finish({
                "message": "Отсутствует профиль пользователя"
            })
        attempt_id = self.get_argument("attempt_id", "")
        if not attempt_id:
            self.set_status(500)
            return self.finish({
                "message": "Отсутствует параметр запроса attempt_id"
            })
        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            attempt_ids=[attempt_id],
            user_ids=[profile.user_id],
            limit=1,
            offset=0,
        )
        await rpc_client.close()
        if not attempts:
            self.log.info(f"User {profile.email} not used profile with attempts {attempt_id}")
            self.set_status(500)
            return self.finish({
                "message": "Отсутствует attempt_id для данного пользователя"
            })
        attempt = attempts[0]
        labs_path = attempt.get('labs_path')
        if not labs_path:
            message = f"User {profile.email} spawned labs without topology {attempt_id}"
            self.log.info(message)
            self.set_status(200)
            return self.finish({
                "labs_path": labs_path,
                "message": message
            })
        git_client = GitClient()
        topology = await git_client.get_topology_file(labs_path=labs_path)
        await git_client.close()
        if not topology:
            message = (
                f"User {profile.email} spawned labs without topology {attempt_id}. "
                f"Topology file {labs_path} is not found"
            )
            self.log.info(message)
            self.set_status(200)
            return self.finish({
                "labs_path": labs_path,
                "message": message,
            })
        self.log.info(f"Topology file {labs_path} found with {attempt_id} and {profile.email}. Start deploy")
        kubectl_topology = KubectlTopology(
            api_client=self.core_api.api_client,
            k8s_api_request_timeout=120,
        )
        namespace = await kubectl_topology.search_namespace_by_attempt_id(attempt_id=attempt_id)
        if not namespace:
            message = f"User {profile.email} namespaces not found by {attempt_id}"
            self.log.info(message)
            self.set_status(500)
            return self.finish({
                "message": message,
            })
        topology = topology.replace("$NAME", namespace)
        try:
            await kubectl_topology.apply(namespace=namespace, yaml_content=topology)
        except Exception as e:
            self.log.error(f"Error applying topology with user {profile.email} and {attempt_id=}: {str(e)}")
            self.set_status(500)
            return self.finish({
                "message": "Error applying topology"
            })
        self.set_status(200)
        message = f"Topology success applying with {attempt_id=}"
        self.log.info(message)
        return self.finish({
            "labs_path": labs_path,
            "message": message,
        })

    def check_xsrf_cookie(self):
        # Отключил хендлер
        pass
