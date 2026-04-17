import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from jupyterhub.handlers import BaseHandler
from tornado import web
from tornado.web import HTTPError

from cmsspawner.spawner.models import UserInfo


@dataclass
class SSOTokenPublicExtraParams:
    attempt_id: str = ""
    pnet_labs_path: str = ""


class FirstStepHandler(BaseHandler):
    route = r"/pnet-lab-addon/api/v1/sso/login"

    async def get(self, *args, **kwargs):
        self.log.info("User login with addon")
        self.clear_login_cookie()
        self.statsd.incr('logout')
        query_string = self.request.query
        self.redirect(f"{SecondStepHandler.route}/{query_string}")


class SecondStepHandler(BaseHandler):
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
        redirect_url = self.get_query_git_params(extra=extra)
        raise HTTPError(
            410,
            "Пока успех"
        )

    async def get_user_profile(self) -> UserInfo | None:
        user = await self.get_current_user()
        if user:
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

    def get_query_git_params(self, extra: SSOTokenPublicExtraParams) -> str | None:
        path = extra.pnet_labs_path.strip("/")
        base_path = path.split("/")[0]
        params = {
            "repo": f"{self.git_url}/{base_path}",
            "urlpath": f"lab/tree/{path}",  # Jupyter notebook open
            "branch": self.git_branch
        }
        query_string = urlencode(params)
        return f"/hub/user-redirect/{extra.attempt_id}/git-pull?{query_string}"
