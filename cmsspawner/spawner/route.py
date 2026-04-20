import asyncio
import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web
from tornado.web import HTTPError

from cmsspawner.spawner.models import UserInfo
from cmsspawner.spawner.rpc import CMSRpcClient


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
        self.clear_login_cookie()
        self.statsd.incr('logout')
        query_string = self.request.query
        self.redirect(f"{SecondStepHandler.route}?{query_string}")

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
        profile = await self.get_user_profile()
        if not profile:
            raise HTTPError(
                400,
                "Отсутствует профиль пользователя. Пожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )

        user = await self.get_current_user()
        if not user:
            raise HTTPError(401, "Пользователь не авторизован")

        self.log.info(f"User {profile.email} login with addon")

        extra = self.get_params_extra()
        if not extra:
            self.log.error(f"Failed to get extra params by user {profile.email}")
            raise HTTPError(
                400,
                "Параметры лабораторной работы неверные. Пожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )

        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            attempt_ids=[extra.attempt_id],
            user_ids=[profile.user_id],
            statuses=["pending", "active"],
            limit=5000,
            offset=0,
        )

        if not attempts:
            raise HTTPError(
                400,
                "Отсутсвует номер попытки. Пожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )

        attempt = attempts[0]
        attempt_id = attempt["attempt_id"]
        attempt_number = str(attempt["id"])

        if attempt_id != extra.attempt_id:
            raise HTTPError(
                400,
                "Номер попытки не совпадает в запросе. Пожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )

        redirect_url = self.get_redirect_complete_params(
            server_name=attempt_number,
            username=user.name,
            lab_url=extra.pnet_labs_path,
        )

        spawner = user.get_spawner(attempt_number)

        # Если сервер уже готов — не ждём ничего, сразу отправляем на целевой URL
        if spawner.ready:
            self.log.info(
                f"Server '{attempt_number}' for user {user.name} is already ready, redirecting to lab"
            )
            self.redirect(redirect_url)
            return

        # Передаём user_options в spawner перед запуском
        spawner.user_options = {"profile": attempt_id}

        # Если сейчас не идёт pending-операция, пробуем инициировать spawn в фоне
        # Даже если spawner уже существует, но сервер не готов — всё равно пробуем запуск.
        if not spawner.pending:
            self.log.info(
                f"Initiating background spawn for server '{attempt_number}' "
                f"(attempt_id={attempt_id}) user={profile.email}"
            )
            asyncio.create_task(
                self._spawn_in_background(
                    user=user,
                    server_name=attempt_number,
                    options={"profile": attempt_id},
                    email=profile.email,
                )
            )
        else:
            self.log.info(
                f"Spawner '{attempt_number}' for user {user.name} already pending={spawner.pending}"
            )

        # Отправляем пользователя на стандартную страницу ожидания JupyterHub.
        # Передаём next, чтобы после успешного запуска уйти на git-pull URL.
        pending_url = self.get_spawn_pending_url(
            username=user.name,
            server_name=attempt_number,
            next_url=redirect_url,
        )
        self.redirect(pending_url)

    async def _spawn_in_background(
            self,
            user,
            server_name: str,
            options: dict,
            email: str,
    ):
        """
        Фоновый запуск спавна.
        Исключения не пробрасываем в запрос — только логируем.
        Ошибка должна быть подхвачена состоянием spawner/pending page JupyterHub.
        """
        try:
            self.log.info(
                f"Background spawn started for user={user.name}, server={server_name}, options={options}"
            )
            await user.spawn(server_name=server_name, options=options)
            self.log.info(
                f"Background spawn completed for user={user.name}, server={server_name}"
            )
        except Exception as e:
            self.log.exception(
                f"Failed to spawn server '{server_name}' for {email}: {e}"
            )

    def get_spawn_pending_url(self, username: str, server_name: str, next_url: str | None = None) -> str:
        """
        Возвращает URL стандартной страницы ожидания JupyterHub.
        """
        base = url_path_join(
            self.hub.base_url,
            "spawn-pending",
            username,
            server_name,
        )
        if next_url:
            return f"{base}?{urlencode({'next': next_url})}"
        return base

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
