import asyncio
import logging

import yaml
from kubernetes_asyncio.client import ApiException, ApiClient, CoreV1Api
from kubernetes_asyncio.client.api.custom_objects_api import CustomObjectsApi

from .utils import setup_logger


class KubectlTopology:
    # Стандартные ресурсы, которые нужно обрабатывать через CoreV1Api
    CORE_RESOURCES = {
        'ConfigMap', 'Secret', 'Service', 'Pod',
        'PersistentVolumeClaim', 'Namespace', 'ServiceAccount'
    }

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
        manifests = list(yaml.safe_load_all(yaml_content))
        self.logger.info(f"Parsed {len(manifests)} manifests from YAML")

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

            # Определяем, какой API использовать
            if api_version == 'v1' and kind in self.CORE_RESOURCES:
                # Стандартные core ресурсы
                await self._apply_core_resource(manifest, kind, namespace, name)
            else:
                # Кастомные ресурсы или ресурсы других API групп
                await self._apply_custom_resource(manifest, api_version, kind, namespace, name)

            self.logger.info(f"Successfully applied {idx}/{total}: {kind}/{name}")

        except ApiException as e:
            if e.status == 409:
                self.logger.info(f"Resource {kind}/{name} already exists in {namespace}, skipping")
            else:
                self.logger.exception(f"Failed to apply {kind}/{name} in {namespace}")
                raise

    async def _apply_core_resource(self, manifest: dict, kind: str, namespace: str, name: str):
        """Применяет стандартный core ресурс через CoreV1Api"""
        core_v1 = CoreV1Api(self.api_client)

        # Маппинг методов для создания
        create_methods = {
            'ConfigMap': core_v1.create_namespaced_config_map,
            'Secret': core_v1.create_namespaced_secret,
            'Service': core_v1.create_namespaced_service,
            'Pod': core_v1.create_namespaced_pod,
            'PersistentVolumeClaim': core_v1.create_namespaced_persistent_volume_claim,
            'ServiceAccount': core_v1.create_namespaced_service_account,
        }

        create_method = create_methods.get(kind)
        if not create_method:
            raise ValueError(f"Unsupported core resource: {kind}")

        await asyncio.wait_for(
            create_method(namespace=namespace, body=manifest),
            timeout=self.k8s_api_request_timeout,
        )

    async def _apply_custom_resource(self, manifest: dict, api_version: str, kind: str, namespace: str, name: str):
        """Применяет кастомный ресурс через CustomObjectsApi"""
        # Парсим group/version
        if '/' in api_version:
            group, version = api_version.split('/', 1)
        else:
            # Для ресурсов типа apps/v1, batch/v1
            raise ValueError(f"Non-core resource without group: {api_version}/{kind}")

        # Определяем plural
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

    @staticmethod
    def _get_plural(kind: str) -> str:
        """Преобразует Kind в plural форму"""
        special_cases = {
            'Endpoints': 'endpoints',
            'EndpointSlice': 'endpointslices',
            'Ingress': 'ingresses',
            'NetworkPolicy': 'networkpolicies',
        }

        if kind in special_cases:
            return special_cases[kind]

        kind_lower = kind.lower()
        if kind.endswith('y'):
            return kind_lower[:-1] + 'ies'
        elif kind.endswith('s'):
            return kind_lower + 'es'
        else:
            return kind_lower + 's'
