import asyncio
import logging

import yaml
from kubernetes_asyncio.client import ApiException, ApiClient, CoreV1Api
from kubernetes_asyncio.client.api.custom_objects_api import CustomObjectsApi

from .utils import setup_logger


class KubectlTopology:

    def __init__(
            self,
            api_client: ApiClient,
            k8s_api_request_timeout: float,
    ):
        self.api_client = api_client
        self.k8s_api_request_timeout = k8s_api_request_timeout
        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start init KubectlTopology')

    async def search_namespace_by_attempt_id(self, attempt_id: str) -> str | None:
        v1 = CoreV1Api(self.api_client)
        label_selector = f"hub.jupyter.org/cms_attempt_id={attempt_id}"
        try:
            ret = await v1.list_pod_for_all_namespaces(label_selector=label_selector)
            namespaces = [
                pod.metadata.namespace
                for pod in ret.items
            ]
        except ApiException as e:
            self.logger.exception(f"Namespace search error by attempt_id={attempt_id}: {e}")
            return None
        if not namespaces:
            self.logger.exception(f"Namespace not found by attempt_id={attempt_id}")
            return None
        self.logger.info(f"Found {namespaces[0]} namespace by {attempt_id}")
        return namespaces[0]

    async def apply(self, yaml_content: str, namespace: str) -> None:
        """Основной метод: применяет манифесты"""
        # Шаг 1: Получаем список всех манифестов из YAML
        manifests = list(yaml.safe_load_all(yaml_content))
        self.logger.info(f"Parsed {len(manifests)} manifests from YAML")

        # Шаг 2: Применяем каждый манифест
        for idx, manifest in enumerate(manifests, start=1):
            if not manifest:
                continue
            await self._apply_manifest(manifest=manifest, namespace=namespace, idx=idx, total=len(manifests))
        return None

    async def _apply_manifest(
            self,
            manifest: dict,
            namespace: str,
            idx: int,
            total: int,
    ):
        """Применяет один манифест"""
        kind, name = "", ""
        try:
            if 'metadata' not in manifest:
                manifest['metadata'] = {}
            if 'namespace' not in manifest['metadata']:
                manifest['metadata']['namespace'] = namespace

            api_version = manifest.get('apiVersion', '')
            kind = manifest.get('kind', '')
            name = manifest.get('metadata', {}).get('name', 'Unknown')
            namespace = manifest['metadata']['namespace']

            self.logger.info(f"Applying {idx}/{total}: {kind}/{name} in namespace {namespace}")

            # Парсим group/version
            if '/' in api_version:
                group, version = api_version.split('/', 1)
            else:
                # Для стандартных ресурсов (v1, apps/v1 и т.д.)
                group = ""
                version = api_version

            plural = self._get_plural(kind)
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

    @staticmethod
    def _get_plural(kind: str) -> str:
        """Преобразует Kind в plural форму"""
        # Специальные случаи
        special_cases = {
            'Endpoints': 'endpoints',
            'EndpointSlice': 'endpointslices',
            'Ingress': 'ingresses',
            'NetworkPolicy': 'networkpolicies',
        }

        if kind in special_cases:
            return special_cases[kind]

        # Общие правила
        kind_lower = kind.lower()
        if kind.endswith('y'):
            return kind_lower[:-1] + 'ies'  # Topology -> topologies
        elif kind.endswith('s'):
            return kind_lower + 'es'  # Ingress -> ingresses (но уже в special_cases)
        else:
            return kind_lower + 's'  # ConfigMap -> configmaps
