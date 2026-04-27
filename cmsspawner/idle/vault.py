import json

from cmsspawner.cms_client.rpc import CMSRpcClient
from cmsspawner.jupyter_client.client import JupyterHubClient


def vault_init():
    with open('/var/run/secrets/app/json', 'r') as f:
        secrets = json.load(f)
    JupyterHubClient.hub_url = secrets["IDLE_API_URL"]
    JupyterHubClient.api_token = secrets["IDLE_API_TOKEN"]
    CMSRpcClient.base_url = secrets["CMS_URL"]
    CMSRpcClient.login = secrets["CMS_LOGIN"]
    CMSRpcClient.password = secrets["CMS_PASSWORD"]
