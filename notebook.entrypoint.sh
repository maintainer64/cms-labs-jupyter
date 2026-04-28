#!/bin/bash
mkdir -p /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension && \
echo '{"locale": "ru_RU"}' > /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension/plugin.jupyterlab-settings && \
chown -R jovyan: /home/jovyan/.jupyter