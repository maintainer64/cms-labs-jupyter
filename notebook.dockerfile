FROM harbor.k8s.cmslabs.ru/proxy_quay_io/jupyter/minimal-notebook:latest
USER root
COPY notebook.requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt
USER ${NB_UID}