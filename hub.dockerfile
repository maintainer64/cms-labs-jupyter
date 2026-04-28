FROM harbor.k8s.cmslabs.ru/proxy_quay_io/jupyterhub/k8s-hub:4.3.3

USER root

COPY . .
RUN pip install .

USER 1000