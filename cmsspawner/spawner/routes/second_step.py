import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from jupyterhub.handlers import BaseHandler
from tornado import web

from cmsspawner.cms_client.rpc import CMSRpcClient
from cmsspawner.git_client.client import GitClient
from cmsspawner.spawner.models import UserInfo
from cmsspawner.spawner.utils import render_template


@dataclass
class SSOTokenPublicExtraParams:
    attempt_id: str = ""


class SecondStepHandler(BaseHandler):
    """
    Хендлер проверяет текущие параметры лабораторной из extra и CMS системы,
    инициирует запуск named-server для попытки и отправляет пользователя
    на стандартную страницу ожидания JupyterHub (spawn-pending).

    После успешного старта пользователь сможет перейти на git-pull URL.
    """

    route = r"/pnet-lab-addon/api/v1/sso/connect"

    @web.authenticated
    async def get(self, *args, **kwargs):
        html = await render_template(
            template_name="lab_waiting.html.jinja2",
            xsrf_token=self.xsrf_token.decode("utf-8"),
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
        labs_path = attempt.get("labs_path")

        if attempt_id != extra.attempt_id:
            self.set_status(400)
            return self.finish({
                "error": "Номер попытки не совпадает в запросе."
            })
        finish_redirect_url = self.get_redirect_complete_params(
            server_name=attempt_number,
            username=user.name,
            labs_path=labs_path or "",
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

            return SSOTokenPublicExtraParams(
                attempt_id=attempt_id,
            )
        except Exception as e:
            self.log.error(f"Failed to decode extra param: {e}")
            return None

    @staticmethod
    def get_redirect_complete_params(server_name: str, username: str, labs_path: str) -> str:
        """
        Создаёт ссылку для перехода на созданный ресурс
        """
        path = labs_path.strip("/")
        base_path = path.split("/")[0]

        params = {
            "repo": f"{GitClient.git_url}/{base_path}",
            "urlpath": f"lab/tree/{path}",
            "branch": GitClient.git_branch,
        }
        query_string = urlencode(params)
        return f"/user/{username}/{server_name}/git-pull?{query_string}"
