#!/usr/bin/env python3
"""
Асинхронный клиент для JupyterHub API.

Поддерживает:
- получение списка пользователей с пагинацией;
- получение списка серверов пользователей;
- остановку default/named сервера;
- удаление named сервера через stop + remove.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import aiohttp
import dateutil.parser

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]
JsonList = list[JsonDict]


class JupyterHubAPIError(RuntimeError):
    """Ошибка ответа JupyterHub API."""

    def __init__(self, status: int, method: str, url: str, body: str = "") -> None:
        self.status = status
        self.method = method
        self.url = url
        self.body = body

        message = f"HTTP {status} on {method} {url}"
        if body:
            message += f": {body}"

        super().__init__(message)


def parse_date(date_string: str | None) -> datetime | None:
    """Преобразует строку даты в timezone-aware datetime в UTC."""

    if not date_string:
        return None

    dt = dateutil.parser.parse(date_string)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def utcnow() -> datetime:
    """Возвращает текущее время в UTC."""

    return datetime.now(timezone.utc)


def url_quote(value: str) -> str:
    """Безопасно экранирует часть URL."""

    return quote(value, safe="")


class JupyterHubClient:
    """Асинхронный клиент для JupyterHub API.
    :param hub_url:
        Базовый URL JupyterHub API.
        Например: http://localhost:8080/hub/api

    :param api_token:
        API-токен администратора.

    :param session:
        Внешняя aiohttp-сессия.
        Если не передана, клиент создаст и закроет свою.

    :param request_timeout:
        Общий таймаут запроса в секундах.
    """

    PAGINATION_ACCEPT_HEADER = "application/jupyterhub-pagination+json"
    hub_url: str = ""
    api_token: str = ""
    _session: aiohttp.ClientSession | None = None
    _request_timeout: int | float = 60

    def __init__(
            self,
    ) -> None:
        self.hub_url = self.hub_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=self._request_timeout)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.api_token}",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрывает внутреннюю aiohttp-сессию, если клиент создал её сам."""
        await self._session.close()
        self._session = None

    def _make_url(self, path_or_url: str) -> str:
        """
        Собирает полный URL.

        Поддерживает:
        - обычные API paths: /users
        - абсолютные URL из пагинации
        - относительные URL вида /hub/api/users?offset=...
        """

        if path_or_url.startswith(("http://", "https://")):
            return path_or_url

        if not path_or_url.startswith("/"):
            path_or_url = f"/{path_or_url}"

        parsed_hub_url = urlparse(self.hub_url)
        hub_api_path = parsed_hub_url.path.rstrip("/")

        # Если JupyterHub вернул в пагинации путь уже с /hub/api,
        # не нужно добавлять hub_url второй раз.
        if (
                parsed_hub_url.scheme
                and parsed_hub_url.netloc
                and hub_api_path
                and (
                path_or_url == hub_api_path
                or path_or_url.startswith(f"{hub_api_path}/")
        )
        ):
            return f"{parsed_hub_url.scheme}://{parsed_hub_url.netloc}{path_or_url}"

        return f"{self.hub_url}{path_or_url}"

    async def _request(
            self,
            method: str,
            path_or_url: str,
            *,
            headers: Mapping[str, str] | None = None,
            **kwargs: Any,
    ) -> Any:
        """Выполняет HTTP-запрос к JupyterHub API."""

        url = self._make_url(path_or_url)
        session = await self._get_session()

        request_headers = self._headers.copy()
        if headers:
            request_headers.update(headers)

        timeout = kwargs.pop("timeout", self._timeout)

        async with session.request(
                method,
                url,
                headers=request_headers,
                timeout=timeout,
                **kwargs,
        ) as response:
            raw_body = await response.read()
            body = raw_body.decode("utf-8", errors="replace")

            if response.status >= 400:
                raise JupyterHubAPIError(
                    status=response.status,
                    method=method,
                    url=url,
                    body=body,
                )

            if response.status == 204 or not raw_body.strip():
                return None

            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body

    async def _get_paginated(
            self,
            path: str,
            params: Mapping[str, Any] | None = None,
    ) -> JsonList:
        """
        Получает все элементы из пагинированного endpoint.

        JupyterHub >= 2.0 возвращает:
        {
            "items": [...],
            "_pagination": {
                "next": {
                    "url": "..."
                }
            }
        }

        Старые версии могут вернуть обычный список.
        """

        items: JsonList = []
        current_url: str | None = path
        current_params: Mapping[str, Any] | None = dict(params or {})

        headers = {
            "Accept": self.PAGINATION_ACCEPT_HEADER,
        }

        while current_url:
            data = await self._request(
                "GET",
                current_url,
                params=current_params,
                headers=headers,
            )

            # Параметры нужны только для первого запроса.
            # Следующий URL из пагинации уже содержит query string.
            current_params = None

            if isinstance(data, list):
                return data

            if not isinstance(data, dict):
                return items

            if "items" not in data:
                return [data]

            page_items = data.get("items") or []
            if not isinstance(page_items, list):
                raise RuntimeError("Invalid JupyterHub pagination response: items is not a list")

            items.extend(page_items)

            pagination = data.get("_pagination") or {}
            next_info = pagination.get("next") or {}

            current_url = next_info.get("url")

        return items

    @staticmethod
    def _server_path(user: str, server_name: str = "") -> str:
        """Возвращает API path для default или named server."""

        user = url_quote(user)

        if server_name:
            return f"/users/{user}/servers/{url_quote(server_name)}"

        return f"/users/{user}/server"

    async def list_users(
            self,
    ) -> JsonList:
        """
        Возвращает список пользователей.
        """

        return await self._get_paginated(
            "/users",
            params={
                "include_stopped_servers": 1,
                "limit": 50,
            }
        )

    async def get_server_info(
            self,
            user: str,
            server_name: str = "",
    ) -> JsonDict | None:
        """Возвращает информацию о сервере пользователя."""

        path = self._server_path(user, server_name)

        try:
            data = await self._request("GET", path)
        except JupyterHubAPIError as exc:
            if exc.status == 404:
                return None

            raise

        return data if isinstance(data, dict) else None

    async def stop_server(
            self,
            user: str,
            server_name: str = "",
    ) -> bool:
        """
        Останавливает сервер.

        :return:
            True — запрос на остановку выполнен;
            False — сервер не найден.
        """

        path = self._server_path(user, server_name)

        try:
            await self._request("DELETE", path, json={"remove": True})
        except JupyterHubAPIError as exc:
            if exc.status == 404:
                logger.debug(
                    "Server not found: user=%s, server=%s",
                    user,
                    server_name or "<default>",
                )
                return False

            raise

        logger.info(
            "Stopped server: user=%s, server=%s",
            user,
            server_name or "<default>",
        )

        return True

    async def delete_server(
            self,
            user: str,
            server_name: str,
    ) -> bool:
        """
        Удаляет named server.

        Для default-сервера удаление невозможно — его можно только остановить.
        """

        if not server_name:
            logger.warning(
                "Default server cannot be removed, it can only be stopped: user=%s",
                user,
            )
            return await self.stop_server(user)

        path = self._server_path(user, server_name)

        try:
            await self._request(
                "DELETE",
                path,
                json={"remove": True},
                headers={"Content-Type": "application/json"},
            )
        except JupyterHubAPIError as exc:
            if exc.status == 404:
                logger.debug(
                    "Named server not found: user=%s, server=%s",
                    user,
                    server_name,
                )
                return False

            raise

        logger.info(
            "Removed named server: user=%s, server=%s",
            user,
            server_name,
        )

        return True

    async def list_servers(
            self,
    ) -> JsonList:
        """
        Возвращает список серверов пользователей.

        Элемент списка:

        {
            "user": "username",
            "server_name": "",
            "full_name": "username",
            "last_activity": datetime | None,
            "started": datetime | None,
            "pending": None | "spawn" | "stop",
            "ready": bool,
            "state": dict
        }
        """
        users = await self.list_users()

        servers: JsonList = []

        for user_info in users:
            user_name = user_info.get("name")
            if not user_name:
                continue

            servers_dict = user_info.get("servers") or {}

            # Старый формат JupyterHub без named servers.
            if not servers_dict and user_info.get("server"):
                servers_dict = {
                    "": {
                        "last_activity": user_info.get("last_activity"),
                        "pending": user_info.get("pending"),
                        "url": user_info.get("server"),
                        "ready": bool(user_info.get("server")),
                        "started": user_info.get("created"),
                    }
                }

            for server_name, server_info in servers_dict.items():
                ready = bool(server_info.get("ready", bool(server_info.get("url"))))
                pending = server_info.get("pending")

                last_activity = (
                        server_info.get("last_activity")
                        or user_info.get("last_activity")
                )

                started = (
                        server_info.get("started")
                        or server_info.get("created")
                )

                servers.append(
                    {
                        "user": user_name,
                        "server_name": server_name,
                        "full_name": (
                            f"{user_name}/{server_name}"
                            if server_name
                            else user_name
                        ),
                        "last_activity": parse_date(last_activity),
                        "started": parse_date(started),
                        "pending": pending,
                        "ready": ready,
                        "state": server_info.get("state") or {},
                    }
                )

        return servers
