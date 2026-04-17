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
    route = r"/pnet-lab-addon/api/v1/sso/login"

    async def get(self, *args, **kwargs):
        self.log.info("User login with addon")
        self.clear_login_cookie()
        self.statsd.incr('logout')
        query_string = self.request.query
        self.redirect(f"{SecondStepHandler.route}?{query_string}")


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
        rpc_client = CMSRpcClient()
        attempts = await rpc_client.list_attempts(
            attempt_ids=[extra.attempt_id],
            user_ids=[user.user_id],
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
        attempt_name = attempt.get('lti_routing_name') or attempt.get("user_name") or f"Attempt {attempt_id}"
        if attempt_id != extra.attempt_id:
            raise HTTPError(
                400,
                "Номер попытки не совпадает в запросе.\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )
        if attempt_id not in user.spawners:
            self.log.info(f"Spawning server '{attempt_id}' for user {profile.email}")
            try:
                await user.spawn(
                    server_name=attempt_id,
                    user_options={"profile": attempt_id, "name": attempt_name}
                )
            except Exception as e:
                self.log.error(f"Failed to spawn server '{attempt_id}' for {profile.email}: {e}")
                raise HTTPError(
                    500,
                    f"{e}\nПожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
                )
        redirect_url = self.get_redirect_complete_params(extra=extra, profile=profile)
        self.redirect(redirect_url)

    async def get_user_profile(self) -> UserInfo | None:
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

    def get_redirect_complete_params(self, extra: SSOTokenPublicExtraParams, profile: UserInfo) -> str:
        path = extra.pnet_labs_path.strip("/")
        base_path = path.split("/")[0]
        params = {
            "repo": f"{self.git_url}/{base_path}",
            "urlpath": f"lab/tree/{path}",  # Jupyter notebook open
            "branch": self.git_branch
        }
        query_string = urlencode(params)
        return f"/user/{profile.username}/{extra.attempt_id}/git-pull?{query_string}"
