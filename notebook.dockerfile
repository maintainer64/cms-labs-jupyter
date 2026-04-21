FROM harbor.k8s.cmslabs.ru/proxy_quay_io/jupyter/minimal-notebook:hub-5.4.4
USER root
COPY --from=harbor.k8s.cmslabs.ru/proxy_ghcr_io/astral-sh/uv:latest /uv /uvx /bin/
COPY notebook.requirements.txt /tmp/requirements.txt
RUN uv pip install \
    --system \
    --no-cache-dir \
    -r /tmp/requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ && \
    rm /tmp/requirements.txt
# Предустановка русской локали для JupyterLab
RUN mkdir -p /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension && \
    echo '{"locale": "ru_RU"}' > /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension/plugin.jupyterlab-settings && \
    chown -R jovyan: /home/jovyan/.jupyter
USER ${NB_UID}