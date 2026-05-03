from typing import Optional

import aiohttp


class GitClient:
    """
    Асинхронный HTTP клиент для работы с GIT API.
    :param git_url: базовый URL сервера с заданием (например, https://example.com/api/v1/rpc)
    :param git_branch: Ветка для скачивания
    :param session: опциональная внешняя сессия aiohttp
    """
    git_url: str = ""
    git_branch: str = "master"
    file_search: str = "topology.template.yaml"
    _session: Optional[aiohttp.ClientSession] = None

    def __init__(self):
        self.git_url = self.git_url.rstrip('/')

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрыть собственную сессию, если она была создана внутри."""
        await self._session.close()
        self._session = None

    async def get_topology_file(self, labs_path: str | None) -> str | None:
        if not labs_path:
            return None
        labs_path = labs_path.strip('/')
        parts = labs_path.split('/')
        possible_paths: list[str] = []
        for i in range(1, len(parts) + 1):
            current_dir = '/'.join(parts[:i])
            file_name = self.file_search
            url = f"{self.git_url}/{current_dir}/-/raw/{self.git_branch}/{file_name}"
            possible_paths.append(url)
        session = await self._get_session()
        for url in possible_paths:
            async with session.get(url, raise_for_status=False, allow_redirects=False) as resp:
                if resp.status != 200:
                    continue
                print(f"founded url: {url}")
                return await resp.text()
        return None
