import json
import os

from .route import RedirectToOIDCPreStepHandler
from .rpc import CMSRpcClient


def vault_init(c):
    with open('/var/run/secrets/app/json', 'r') as f:
        secrets = json.load(f)
    c.KubeSpawner.slug_scheme = "escape"
    c.KubeSpawner.storage_extra_labels = {'hub.jupyter.org/username': '{escaped_username}'}
    c.KubeSpawner.extra_labels = {'hub.jupyter.org/username': '{escaped_username}'}
    c.JupyterHub.cookie_secret = secrets["COOKIE_SECRET"]
    c.JupyterHub.db_url = secrets["MYSQL_URL"]
    os.environ["MYSQL_PWD"] = secrets["MYSQL_PASSWORD"]
    c.GenericOAuthenticator.client_id = secrets["OIDC_CLIENT_ID"]
    c.GenericOAuthenticator.client_secret = secrets["OIDC_CLIENT_SECRET"]
    c.GenericOAuthenticator.oauth_callback_url = secrets["OIDC_CALLBACK_URL"]
    c.GenericOAuthenticator.authorize_url = secrets["OIDC_AUTHORIZE_URL"]
    c.GenericOAuthenticator.token_url = secrets["OIDC_TOKEN_URL"]
    c.GenericOAuthenticator.userdata_url = secrets["OIDC_USERDATA_URL"]
    CMSRpcClient.base_url = secrets["CMS_URL"]
    CMSRpcClient.login = secrets["CMS_LOGIN"]
    CMSRpcClient.password = secrets["CMS_PASSWORD"]

    c.JupyterHub.extra_handlers = [
        (r'/pnet-lab-addon/api/v1/sso/login', RedirectToOIDCPreStepHandler),
    ]
