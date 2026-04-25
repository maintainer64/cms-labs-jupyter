import asyncio
import base64
import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode

from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web
from tornado.web import HTTPError

from cmsspawner.spawner.models import UserInfo
from cmsspawner.spawner.rpc import CMSRpcClient
from cmsspawner.spawner.utils import render_template


@dataclass
class SSOTokenPublicExtraParams:
    attempt_id: str = ""
    pnet_labs_path: str = ""


class FirstStepHandler(BaseHandler):
    """
    Хендлер разлогинивает пользователя (чтобы стереть данные предыдущего пользователя на этом компьютере)
    И отправляет через на обработчик ниже. @web.authenticated гарантирует появление пользователя в системе
    Цепочка редиректов получит свежий профиль пользователя.
    Не забывает параметры extra прокинуть с текущей страницы
    """
    route = r"/pnet-lab-addon/api/v1/sso/login"

    async def get(self, *args, **kwargs):
        self.log.info("User login with addon")
        self.clear_all_cookies()
        self.statsd.incr('logout')
        query_string = self.request.query
        html = await render_template(
            template_name="auto_redirect.html.jinja2",
            redirect_url=f"{SecondStepHandler.route}?{query_string}"
        )
        return self.finish(html)


class SecondStepHandler(BaseHandler):
    """
    Хендлер проверяет текущие параметры лабораторной из extra и CMS системы,
    инициирует запуск named-server для попытки и отправляет пользователя
    на стандартную страницу ожидания JupyterHub (spawn-pending).

    После успешного старта пользователь сможет перейти на git-pull URL.
    """

    git_url: str = ""
    git_branch: str = "master"
    route = r"/pnet-lab-addon/api/v1/sso/connect"

    @web.authenticated
    async def get(self, *args, **kwargs):
        html = await render_template(
            template_name="lab_waiting.html.jinja2",
        )
        return self.finish(html)

    @web.authenticated
    async def post(self, *args, **kwargs):
        profile = await self.get_user_profile()
        if not profile:
            self.set_status(400)
            return self.finish({
                "error": "Отсутствует профиль пользователя."
            })

        user = await self.get_current_user()
        if not user:
            self.set_status(400)
            return self.finish({
                "error": "Пользователь не авторизован"
            })

        self.log.info(f"User {profile.email} second step with addon")

        extra = self.get_params_extra()
        if not extra:
            self.log.error(f"Failed to get extra params by user {profile.email}")
            self.set_status(400)
            return self.finish({
                "error": "Параметры лабораторной работы неверные."
            })

        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            attempt_ids=[extra.attempt_id],
            user_ids=[profile.user_id],
            statuses=["pending", "active"],
            limit=5000,
            offset=0,
        )

        if not attempts:
            self.set_status(400)
            return self.finish({
                "error": "Отсутсвует номер попытки."
            })

        attempt = attempts[0]
        attempt_id = attempt["attempt_id"]
        attempt_number = str(attempt["id"])

        if attempt_id != extra.attempt_id:
            self.set_status(400)
            return self.finish({
                "error": "Номер попытки не совпадает в запросе."
            })
        finish_redirect_url = self.get_redirect_complete_params(
            server_name=attempt_number,
            username=user.name,
            lab_url=extra.pnet_labs_path,
        )
        return self.finish({
            "attempt_number": attempt_number,
            "lti_routing_name": attempt.get("lti_routing_name"),
            "display_name": profile.name,
            "username": profile.username,
            "server_name": attempt_number,  # это ID сервера (named server)
            "attempt_id": attempt_id,  # это profile для спавна
            "redirect_url": finish_redirect_url,
        })

    def check_xsrf_cookie(self):
        """Отключаем XSRF для этого handler'а — аутентификация через @web.authenticated"""
        pass

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

    def get_params_extra(self) -> SSOTokenPublicExtraParams | None:
        """
        Декодирует строку extra из base64 в DTO
        """
        extra_b64 = self.get_argument("extra", "")
        if not extra_b64:
            return None

        try:
            decoded_bytes = base64.b64decode(extra_b64)
            extra_params = json.loads(decoded_bytes.decode("utf-8"))

            attempt_id = extra_params.get("attempt_id", "") or ""
            pnet_labs_path = extra_params.get("pnet_labs_path", "") or ""

            return SSOTokenPublicExtraParams(
                attempt_id=attempt_id,
                pnet_labs_path=pnet_labs_path,
            )
        except Exception as e:
            self.log.error(f"Failed to decode extra param: {e}")
            return None

    def get_redirect_complete_params(self, server_name: str, username: str, lab_url: str) -> str:
        """
        Создаёт ссылку для перехода на созданный ресурс
        """
        path = lab_url.strip("/")
        base_path = path.split("/")[0]

        params = {
            "repo": f"{self.git_url}/{base_path}",
            "urlpath": f"lab/tree/{path}",
            "branch": self.git_branch,
        }
        query_string = urlencode(params)
        return f"/user/{username}/{server_name}/git-pull?{query_string}"
