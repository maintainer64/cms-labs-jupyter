from jupyterhub.handlers import BaseHandler


class RedirectToOIDCPreStepHandler(BaseHandler):
    async def get(self, *args, **kwargs):
        self.log.info("User login with addon")
        self.clear_login_cookie()
        self.statsd.incr('logout')
        self.redirect("/hub/oauth_login")
