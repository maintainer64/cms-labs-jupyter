import json
from typing import Dict, Any, Tuple

import yaml
from jupyterhub.handlers import BaseHandler
from kubernetes_asyncio.config import load_config
from kubespawner.clients import shared_client
from tornado import web

from cmsspawner.spawner.models import UserInfo
from cmsspawner.spawner.spawner import CMSSpawner
from cmsspawner.spawner.utils import render_template


class TopologyHandler(BaseHandler):
    route = r"/containerlab/topology"

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

    def _parse_request_body(self) -> Tuple[str, str] | None:
        """
        Парсит тело запроса и извлекает name и namespace
        Возвращает (topology_name, namespace) или None в случае ошибки
        """
        try:
            body = json.loads(self.request.body)
            topology_name = body.get("name")
            namespace = body.get("namespace")

            if not topology_name or not namespace:
                self.set_status(400)
                self.finish({
                    "error": "Параметры 'name' и 'namespace' обязательны."
                })
                return None

            return topology_name, namespace
        except json.JSONDecodeError:
            self.set_status(400)
            self.finish({
                "error": "Неверный формат JSON."
            })
            return None

    async def _get_topology(self, custom_api: Any, topology_name: str) -> Dict[str, Any] | None:
        """
        Получает топологию из Kubernetes
        """
        try:
            topology = await custom_api.get_namespaced_custom_object(
                group="clabernetes.containerlab.dev",
                version="v1alpha1",
                namespace=topology_name,
                plural="topologies",
                name=topology_name
            )
            return topology
        except Exception as e:
            self.log.error(f"Error getting topology: {str(e)}")
            return None

    @staticmethod
    def _parse_topology_nodes(topology: Dict[str, Any]) -> Dict[str, Any]:
        """
        Парсит YAML определения топологии и извлекает ноды
        """
        topology_def = yaml.safe_load(topology["spec"]["definition"]["containerlab"])
        return topology_def.get("topology", {}).get("nodes", {})

    @staticmethod
    async def _get_services(core_api: Any, namespace: str):
        """
        Получает все сервисы в namespace
        """
        return await core_api.list_namespaced_service(namespace=namespace)

    @staticmethod
    async def _get_http_routes(custom_api: Any, namespace: str) -> Dict[str, Any]:
        """
        Получает все HTTPRoutes в namespace
        """
        try:
            return await custom_api.list_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace=namespace,
                plural="httproutes"
            )
        except:
            try:
                return await custom_api.list_namespaced_custom_object(
                    group="gateway.networking.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="httproutes"
                )
            except:
                return {"items": []}

    @staticmethod
    def _find_external_ip(node_name: str, services) -> str | None:
        """
        Находит EXTERNAL-IP для указанной ноды в списке сервисов
        """
        for svc in services.items:
            if svc.metadata.name == node_name and svc.spec.type == "LoadBalancer":
                if svc.status.load_balancer.ingress:
                    return svc.status.load_balancer.ingress[0].ip
        return None

    @staticmethod
    def _find_http_route_hostname(node_name: str, http_routes: Dict[str, Any]) -> str | None:
        """
        Находит hostname из HTTPRoute для указанной ноды
        """
        for route in http_routes.get("items", []):
            rules = route.get("spec", {}).get("rules", [])
            route_matches = False

            for rule in rules:
                backend_refs = rule.get("backendRefs", [])
                for backend in backend_refs:
                    if backend.get("name") == node_name:
                        route_matches = True
                        break
                if route_matches:
                    break

            if route_matches:
                hostnames = route.get("spec", {}).get("hostnames", [])
                if hostnames:
                    return hostnames[0]
        return None

    @web.authenticated
    async def post(self, *args, **kwargs):
        # Получаем профиль пользователя
        profile = await self.get_user_profile()
        if not profile:
            self.set_status(400)
            return self.finish({
                "error": "Отсутствует профиль пользователя."
            })
        topology_name = self.get_argument("topology_name", "")
        if not topology_name:
            self.set_status(500)
            return self.finish({
                "error": "Отсутствует параметр топологии"
            })

        self.log.info(f"User {profile.email} get topology {topology_name}")

        # Инициализируем Kubernetes клиенты
        await load_config(
            host=CMSSpawner.k8s_api_host,
            ssl_ca_cert=CMSSpawner.k8s_api_ssl_ca_cert,
            verify_ssl=CMSSpawner.k8s_api_verify_ssl,
        )
        custom_api = shared_client("CustomObjectsApi")
        core_api = shared_client("CoreV1Api")

        # Получаем топологию
        topology = await self._get_topology(custom_api=custom_api, topology_name=topology_name)
        if not topology:
            self.set_status(404)
            return self.finish({
                "error": "Топология не найдена"
            })
        try:
            # Получаем ноды из топологии
            nodes = self._parse_topology_nodes(topology)

            # Получаем сервисы и HTTPRoutes
            services = await self._get_services(core_api=core_api, namespace=topology_name)
            http_routes = await self._get_http_routes(custom_api=custom_api, namespace=topology_name)

            # Формируем результат
            result_nodes = [
                {
                    {
                        "name": node_name,
                        "external_ip": self._find_external_ip(node_name, services),
                        "http_route": self._find_http_route_hostname(node_name, http_routes)
                    }
                } for node_name in nodes.keys()
            ]

            return self.finish({
                "nodes": result_nodes
            })

        except Exception as e:
            self.log.error(f"Error processing topology: {str(e)}")
            self.set_status(500)
            return self.finish({
                "error": f"Ошибка обработки топологии: {str(e)}"
            })

    @web.authenticated
    async def get(self, *args, **kwargs):
        html = await render_template(
            template_name="auto_redirect.html.jinja2",
            xsrf_token=self.xsrf_token.decode("utf-8"),
        )
        return self.finish(html)
