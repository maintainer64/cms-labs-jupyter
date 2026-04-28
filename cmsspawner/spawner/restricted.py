import re
from tornado import web
from jupyterhub.handlers.base import BaseHandler

# Список регулярок для запрещенных путей
FORBIDDEN_PATTERNS = [
    re.compile(r'^/hub/home/?$'),  # Главная
    re.compile(r'^/hub/spawn/?$'),  # Страница выбора опций (общая)
    re.compile(r'^/hub/spawn/[^/]+/?$'),  # /hub/spawn/:username
    re.compile(r'^/hub/spawn-pending/?$'),  # /hub/spawn-pending (общая)
    re.compile(r'^/hub/spawn-pending/[^/]+/?$'),  # /hub/spawn-pending/:username
]

original_prepare = BaseHandler.prepare


async def middleware_restricted(self):
    # Проверяем совпадение пути с любым из паттернов
    path = self.request.path
    if any(p.match(path) for p in FORBIDDEN_PATTERNS):
        raise web.HTTPError(403, "Доступ к странице ограничен")
    return await original_prepare(self)

# Подменяем метод во всех обработчиках
BaseHandler.prepare = middleware_restricted
