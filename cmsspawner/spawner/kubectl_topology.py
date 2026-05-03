import asyncio
import logging

import yaml
from kubernetes_asyncio.client import ApiException, ApiClient
from kubernetes_asyncio.client.api.custom_objects_api import CustomObjectsApi

from .utils import setup_logger, render_template


class KubectlTopology:
    hostname_suffix = ''

    def __init__(
            self,
            api_client: ApiClient,
            namespace: str,
            k8s_api_request_timeout: float,
    ):
        self.api_client = api_client
        self.namespace = namespace
        self.k8s_api_request_timeout = k8s_api_request_timeout
        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start init KubectlTopology')

    async def apply(self, yaml_content: str) -> None:
        """Основной метод: применяет манифесты и создает HTTPRoute для нод топологий"""

        # Шаг 1: Применяем все манифесты
        manifests = await self._apply_manifests(yaml_content=yaml_content)

        # Шаг 3: Проходимся по каждому манифесту и проверяем, является ли он Topology
        for manifest in manifests:
            if not manifest:
                continue

            # Проверяем - это Topology от clabernetes?
            if not self._is_clabernetes_topology(manifest):
                continue
            topology_name = manifest.get('metadata', {}).get('name', 'Unknown')

            self.logger.info(f"Found Clabernetes Topology: {topology_name}")

            # Получаем список нод из топологии
            nodes = self._extract_topology_nodes(manifest)

            if not nodes:
                self.logger.warning(f"No nodes found in topology {topology_name}")
                continue

            self.logger.info(f"Found {len(nodes)} nodes in topology {topology_name}: {list(nodes.keys())}")

            # Для каждой ноды создаем дополнительные манифесты
            for node_name in nodes.keys():
                topology_additional_yaml_content = await render_template(
                    template_name="topology-additional.yaml.jinja2",
                    node_name=node_name,
                    namespace=self.namespace,
                    hostname_suffix=self.hostname_suffix,
                )
                await self._apply_manifests(yaml_content=topology_additional_yaml_content)

    @staticmethod
    def _is_clabernetes_topology(manifest: dict) -> bool:
        """Проверяет, является ли манифест Topology от clabernetes"""
        api_version = manifest.get('apiVersion', '')
        kind = manifest.get('kind', '')
        return kind == 'Topology' and 'clabernetes.containerlab.dev' in api_version

    def _extract_topology_nodes(self, topology_manifest: dict) -> dict:
        """Извлекает список нод из Topology манифеста"""
        try:
            # Получаем containerlab YAML из spec.definition.containerlab
            containerlab_yaml = topology_manifest.get('spec', {}).get('definition', {}).get('containerlab', '')

            if not containerlab_yaml:
                return {}

            # Парсим вложенный YAML
            containerlab = yaml.safe_load(containerlab_yaml)

            # Извлекаем ноды из topology.nodes
            nodes = containerlab.get('topology', {}).get('nodes', {})

            return nodes

        except Exception as e:
            self.logger.exception(f"Failed to extract nodes from topology manifest")
            return {}

    async def _create_httproute_for_node(
            self,
            node_name: str,
            topology_name: str,
            namespace: str
    ):
        """Создает HTTPRoute манифесты для одной ноды"""
        self.logger.info(f"Creating HTTPRoute for node: {node_name}")

        # Рендерим HTTP Redirect манифест
        http_redirect_yaml = self._render_http_redirect_template(
            node_name=node_name,
            topology_name=topology_name,
            namespace=namespace
        )

        # Рендерим HTTPS Route манифест
        https_route_yaml = self._render_https_route_template(
            node_name=node_name,
            topology_name=topology_name,
            namespace=namespace
        )

        # Применяем оба манифеста
        await self._apply_httproute_manifest(http_redirect_yaml)
        await self._apply_httproute_manifest(https_route_yaml)

        self.logger.info(f"Successfully created HTTPRoute for node: {node_name}")

    async def _apply_manifest(self, manifest: dict, idx: int, total: int):
        """Применяет один манифест"""
        try:
            if 'metadata' not in manifest:
                manifest['metadata'] = {}
            if 'namespace' not in manifest['metadata']:
                manifest['metadata']['namespace'] = self.namespace

            api_version = manifest.get('apiVersion', '')
            kind = manifest.get('kind', '')
            name = manifest.get('metadata', {}).get('name', 'Unknown')
            namespace = manifest['metadata']['namespace']

            # Парсим group/version
            group, version = api_version.split('/', 1)

            # Определяем plural
            if kind.endswith('y'):
                plural = kind[:-1].lower() + 'ies'  # Topology -> topologies
            else:
                plural = kind.lower() + 's'

            self.logger.info(f"Applying {idx}/{total}: {kind}/{name} in namespace {namespace}")

            custom_api = CustomObjectsApi(api_client=self.api_client)

            await asyncio.wait_for(
                custom_api.create_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    body=manifest,
                ),
                timeout=self.k8s_api_request_timeout,
            )

            self.logger.info(f"Successfully applied {idx}/{total}: {kind}/{name}")

        except ApiException as e:
            if e.status == 409:
                self.logger.info(f"Resource {kind}/{name} already exists in {namespace}, skipping")
            else:
                self.logger.exception(f"Failed to create {kind}/{name} in {namespace}")
                raise

    async def _apply_manifests(self, yaml_content: str) -> list:
        # Шаг 1: Получаем список всех манифестов из YAML
        manifests = list(yaml.safe_load_all(yaml_content))
        self.logger.info(f"Parsed {len(manifests)} manifests from YAML")

        # Шаг 2: Применяем каждый манифест
        for idx, manifest in enumerate(manifests, start=1):
            if not manifest:
                continue
            await self._apply_manifest(manifest, idx, len(manifests))
        return manifests
