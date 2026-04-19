import json
import os

from .route import FirstStepHandler, SecondStepHandler
from .spawner import CMSSpawner
from .rpc import CMSRpcClient


def extract_display_name(authenticator, handler, authentication):
    auth_state = authentication.get('auth_state', {})
    oauth_user = auth_state.get('oauth_user', {})
    real_name = oauth_user.get('name') or oauth_user.get('display_name')
    if real_name:
        authentication['auth_state']['display_name'] = real_name
        authentication['display_name'] = real_name
    return authentication


def vault_init(c):
    with open('/var/run/secrets/app/json', 'r') as f:
        secrets = json.load(f)
    c.KubeSpawner.slug_scheme = "escape"
    c.KubeSpawner.storage_extra_labels = {'hub.jupyter.org/username': '{escaped_username}'}
    c.KubeSpawner.extra_labels = {'hub.jupyter.org/username': '{escaped_username}'}
    c.JupyterHub.cookie_secret = secrets["COOKIE_SECRET"]
    os.environ['JUPYTERHUB_CRYPT_KEY'] = secrets["JUPYTERHUB_CRYPT_KEY"]
    c.JupyterHub.db_url = secrets["MYSQL_URL"]
    os.environ["MYSQL_PWD"] = secrets["MYSQL_PASSWORD"]
    c.GenericOAuthenticator.client_id = secrets["OIDC_CLIENT_ID"]
    c.GenericOAuthenticator.client_secret = secrets["OIDC_CLIENT_SECRET"]
    c.GenericOAuthenticator.oauth_callback_url = secrets["OIDC_CALLBACK_URL"]
    c.GenericOAuthenticator.authorize_url = secrets["OIDC_AUTHORIZE_URL"]
    c.GenericOAuthenticator.token_url = secrets["OIDC_TOKEN_URL"]
    c.GenericOAuthenticator.userdata_url = secrets["OIDC_USERDATA_URL"]
    c.GenericOAuthenticator.post_auth_hook = extract_display_name
    CMSRpcClient.base_url = secrets["CMS_URL"]
    CMSRpcClient.login = secrets["CMS_LOGIN"]
    CMSRpcClient.password = secrets["CMS_PASSWORD"]

    SecondStepHandler.git_url = secrets["CMS_TASK_URL"]
    SecondStepHandler.git_branch = secrets["CMS_TASK_BRANCH"]

    # Изменяем конфигурацию
    c.JupyterHub.extra_handlers = [
        (FirstStepHandler.route, FirstStepHandler),
        (SecondStepHandler.route, SecondStepHandler),
    ]
    # Разрешает использовать 5 серверов
    c.JupyterHub.allow_named_servers = True
    c.JupyterHub.named_server_limit_per_user = 5
    # Подменяем класс spawner_class
    c.JupyterHub.spawner_class = CMSSpawner
    # Подключаем Middleware для hub
    from .restricted import FORBIDDEN_PATTERNS  # noqa
