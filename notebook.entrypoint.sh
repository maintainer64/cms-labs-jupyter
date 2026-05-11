#!/bin/bash
# Ваши настройки JupyterLab
mkdir -p /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension && \
echo '{"locale": "ru_RU"}' > /home/jovyan/.jupyter/lab/user-settings/@jupyterlab/translation-extension/plugin.jupyterlab-settings
# Новый блок: стартовые скрипты IPython
mkdir -p /home/jovyan/.ipython/profile_default/startup
if [ -d /opt/ipython_startup ]; then
    cp -r /opt/ipython_startup/. /home/jovyan/.ipython/profile_default/startup/
fi
# Возвращаем права пользователю jovyan (если контейнер стартует от root, что в Jupyter обычно бывает)
chown -R jovyan: /home/jovyan/.jupyter /home/jovyan/.ipython

# Запускаем команду, переданную в контейнер
exec "$@"