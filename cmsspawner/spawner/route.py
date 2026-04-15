import base64
import json
from dataclasses import dataclass
from urllib.parse import urlparse

from jupyterhub.handlers import BaseHandler
from tornado.web import HTTPError


@dataclass
class SSOTokenPublicExtraParams:
    attempt_id: str = ""
    pnet_labs_path: str = ""


class RedirectToOIDCPreStepHandler(BaseHandler):
    async def get(self, *args, **kwargs):
        self.log.info("User login with addon")
        self.clear_login_cookie()
        self.statsd.incr('logout')
        extra = self.get_params_extra()
        if not extra:
            self.log.error("Failed to get extra params")
            raise HTTPError(
                400,
                "Параметры лабораторной работы неверные. Пожалуйста, вернитесь в Moodle и попробуйте запустить лабораторную работу снова."
            )
        self.redirect(extra.pnet_labs_path)

    def get_params_extra(self) -> SSOTokenPublicExtraParams | None:
        extra_b64 = self.get_argument("extra", "")
        if not extra_b64:
            return None
        try:
            decoded_bytes = base64.b64decode(extra_b64)
            extra_params = json.loads(decoded_bytes)
            attempt_id = extra_params["attempt_id"] or ""
            pnet_labs_path = extra_params["pnet_labs_path"] or ""
        except Exception as e:
            self.log.error(f"Failed to decode extra param: {e}")
            return None
        if not pnet_labs_path.startswith("http"):
            return None
        try:
            parsed_url = urlparse(pnet_labs_path)
        except Exception as e:
            self.log.error(f"Failed to decode extra param pnet_labs_path: {e}")
            return None
        if parsed_url.netloc != self.request.host:
            self.log.error(f"Failed to decode extra param pnet_labs_path: {parsed_url.netloc}")
            return None
        return SSOTokenPublicExtraParams(
            attempt_id=attempt_id,
            pnet_labs_path=pnet_labs_path,
        )
