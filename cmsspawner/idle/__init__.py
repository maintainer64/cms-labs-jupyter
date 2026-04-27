import logging

from cmsspawner.cms_client.rpc import CMSRpcClient
from cmsspawner.idle.vault import vault_init
from cmsspawner.jupyter_client.client import JupyterHubClient
from cmsspawner.spawner.utils import setup_logger

logger = setup_logger(__name__, logging.INFO)


async def clear_server(
        jupyterhub_client: JupyterHubClient,
        user: str,
        server_name: str,
):
    try:
        await jupyterhub_client.stop_server(
            user=user,
            server_name=server_name,
        )
    except Exception as e:
        logger.exception(f"Failed to stop server {server_name}. Error: {e}")

    try:
        return await jupyterhub_client.delete_server(
            user=user,
            server_name=server_name,
        )
    except Exception as e:
        logger.exception(f"Failed to delete server {server_name}. Error: {e}")
    return False


async def main():
    vault_init()
    rpc_client = CMSRpcClient()
    jupyterhub_client = JupyterHubClient()
    # Получаем все серверы, преобразуем в словарь по server_name (номер попытки)
    all_servers = await jupyterhub_client.list_servers(include_inactive=True)
    servers_by_attempt = {
        str(server["server_name"]): server
        for server in all_servers
        if server.get("server_name", "")
    }
    logger.info(f"Found {len(servers_by_attempt)} servers JupyterHub")
    all_attempts = await rpc_client.list_attempts(
        statuses=["pending", "active", "terminating"],
        limit=5000,
        offset=0,
    )
    logger.info(f"Found {len(all_attempts)} attempts CMS")
    cms_attempt_request_list = []

    for external_attempt in all_attempts:
        attempt_status = external_attempt["status"]
        attempt_number = str(external_attempt["id"])  # номер попытки
        attempt_id = external_attempt["attempt_id"]
        cms_attempt_request = {
            "attempt_id": attempt_id,
            "status": "active",
        }
        # Если статус completed - ничего не делаем
        if attempt_status == "completed":
            logger.info(f"Attempt {attempt_number} id={attempt_id} completed, skipping")
            continue
        # Если нет сервера с таким номером попытки — сообщаем и завершаем обработку
        if attempt_number not in servers_by_attempt:
            # Если pending, то возможно запрос ещё не дошёл
            if attempt_status == "pending":
                logger.info(f"No server JupyterHub found for attempt {attempt_number} (id={attempt_id}). But pending")
                continue
            logger.info(f"No server JupyterHub found for attempt {attempt_number} (id={attempt_id})")
            cms_attempt_request["status"] = "completed"
            cms_attempt_request_list.append(cms_attempt_request)
            continue
        server = servers_by_attempt[attempt_number]
        # Если статус terminating — отправляем активное состояние, затем останавливаем сервер и удаляем ресурсы
        if attempt_status == "terminating":  # используем статус из вашего кода
            logger.info(f"Sending active state for terminating attempt {attempt_number}")
            # Отправляем активное состояние с последним состоянием
            # Завершаем операцию: стопаем сервер и удаляем ресурсы
            logger.info(f"Stopping server for attempt {attempt_number} (id={attempt_id})")
            done = await clear_server(jupyterhub_client, server['user'], server["server_name"])
            if done:
                cms_attempt_request["status"] = "completed"
            del servers_by_attempt[attempt_number]
            cms_attempt_request_list.append(cms_attempt_request)
            continue
        # Для всех остальных статусов - отправляем активное состояние
        logger.info(f"Sending active state for attempt {attempt_number} (status={attempt_status})")
        cms_attempt_request_list.append(cms_attempt_request)
    if not cms_attempt_request_list:
        logger.info(f"No server JupyterHub found for all attempts")
        return len(cms_attempt_request_list)
    logger.info(f"Sending active state for all attempts {len(cms_attempt_request_list)}")
    await rpc_client.update_attempts(models=cms_attempt_request_list)
    await rpc_client.close()
    await jupyterhub_client.close()
    return len(cms_attempt_request_list)
