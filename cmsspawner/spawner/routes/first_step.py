from jupyterhub.handlers import BaseHandler

from cmsspawner.spawner.routes.second_step import SecondStepHandler
from cmsspawner.spawner.utils import render_template


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
            redirect_url=f"{SecondStepHandler.route}?{query_string}",
            xsrf_token=self.xsrf_token.decode("utf-8"),
        )
        return self.finish(html)
