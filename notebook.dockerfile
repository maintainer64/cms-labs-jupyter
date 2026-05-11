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
COPY ipython_startup/ /opt/ipython_startup/
RUN chmod -R a+r /opt/ipython_startup
COPY notebook.entrypoint.sh /usr/local/bin/notebook.entrypoint.sh
USER ${NB_UID}