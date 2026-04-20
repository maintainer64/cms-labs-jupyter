import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from jupyterhub.handlers import BaseHandler
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
    Хендлер проверяет текущие параметры лабораторной из extra и CMS системы и создаёт под ноутбука
    Затем редиректит на страницу с созданным сервером и gitPull параметрами для клонирования задания в
    созданное пространство
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
                "Отсутствует профиль пользователя.\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )
        user = await self.get_current_user()
        self.log.info(f"User {profile.email} login with addon")
        extra = self.get_params_extra()
        if not extra:
            self.log.error(f"Failed to get extra params by user {profile.email}")
            raise HTTPError(
                400,
                "Параметры лабораторной работы неверные.\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
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
                "Отсутсвует номер попытки.\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )
        attempt = attempts[0]
        attempt_id = attempt['attempt_id']
        attempt_number = str(attempt['id'])
        if attempt_id != extra.attempt_id:
            raise HTTPError(
                400,
                "Номер попытки не совпадает в запросе.\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )
        if attempt_number not in user.spawners:
            self.log.info(f"Spawning server '{attempt_id}' for user {profile.email}")
            try:
                await user.spawn(
                    server_name=attempt_number,
                    options={"profile": attempt_id}
                )
            except Exception as e:
                self.log.error(f"Failed to spawn server '{attempt_id}' for {profile.email}: {e}")
                raise HTTPError(
                    500,
                    f"{e}\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
                )
        redirect_url = self.get_redirect_complete_params(
            server_name=attempt_number,
            username=profile.username,
            lab_url=extra.pnet_labs_path,
        )
        self.redirect(redirect_url)

    async def get_user_profile(self) -> UserInfo | None:
        """
        Получает профиль текущего пользователя из данных токена CMS
        :return: Профиль пользователя или NULL
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
        Код декодирует строку extra base64 в приятный DTO
        :return: DTO с параметрами о попытке и данными лабы от CMS системы при переходе
        """
        extra_b64 = self.get_argument("extra", "")
        if not extra_b64:
            return None
        try:
            decoded_bytes = base64.b64decode(extra_b64)
            extra_params = json.loads(decoded_bytes)
            attempt_id = extra_params["attempt_id"] or ""
            pnet_labs_path = extra_params["pnet_labs_path"] or ""
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
        :param server_name - название созданного сервера + уникальная попытка сдачи лабы
        :param lab_url - <Репозиторий в группе задач> + <Путь до файла ipub для открытия>
        :param username: Профиль текущего пользователя
        :return: Строка перехода для синхронизации репозитория в простраство созданного ноутбука пользователя
        """
        path = lab_url.strip("/")
        base_path = path.split("/")[0]
        params = {
            "repo": f"{self.git_url}/{base_path}",
            "urlpath": f"lab/tree/{path}",  # Jupyter notebook open
            "branch": self.git_branch
        }
        query_string = urlencode(params)
        return f"/user/{username}/{server_name}/git-pull?{query_string}"
