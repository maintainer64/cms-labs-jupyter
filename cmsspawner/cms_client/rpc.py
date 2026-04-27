import base64
import uuid
from typing import Any, Dict, List, Optional

import aiohttp


class CMSRpcClient:
    """
    Асинхронный JSON‑RPC клиент для работы с CMS API.
    :param base_url: базовый URL сервера (например, https://example.com/api/v1/rpc)
    :param login: Логин сервиса для авторизации
    :param password: Пароль сервиса для авторизации
    :param session: опциональная внешняя сессия aiohttp
    """
    base_url: str | None = None
    login: str | None = None
    password: str | None = None
    _session: Optional[aiohttp.ClientSession] = None

    def __init__(self):
        self.base_url = self.base_url.rstrip('/')

    @property
    def auth_header(self) -> str:
        credentials = f"{self.login}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрыть собственную сессию, если она была создана внутри."""
        await self._session.close()
        self._session = None

    async def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнить JSON‑RPC запрос и вернуть результат (или выбросить исключение)."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        async with session.post(self.base_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text}")
            data = await resp.json()
            if "error" in data:
                error = data["error"]
                raise RuntimeError(f"JSON‑RPC error: {error}")
            return data.get("result", {})

    async def list_attempts(
            self,
            attempt_ids: Optional[List[str]] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None,
            server_client_ids: Optional[List[str]] = None,
            statuses: Optional[List[str]] = None,
            user_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получить список попыток LTI по заданным фильтрам.

        Возвращает список моделей (каждая модель — словарь с полями attempt_id, user_id, status и т.д.).
        """
        params: Dict[str, Any] = {}
        if attempt_ids is not None:
            params["attempt_ids"] = attempt_ids
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if server_client_ids is not None:
            params["server_client_ids"] = server_client_ids
        if statuses is not None:
            params["statuses"] = statuses
        if user_ids is not None:
            params["user_ids"] = list(map(int, user_ids))

        result = await self._request("lti_attempt.list_external", params)
        return result.get("model", [])

    async def update_attempts(
            self, models: List[Dict[str, Any]]
    ) -> int:
        """
        Обновить статус и/или результат одной или нескольких попыток.

        :param models: список словарей, каждый должен содержать как минимум
                       "attempt_id", "status" и/или "result".
        :return: количество обновлённых записей (count)
        """
        params = {"models": models}
        result = await self._request("lti_attempt.update", params)
        return result.get("count", 0)
