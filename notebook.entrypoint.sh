#!/bin/sh

# This file is a Jupyter Docker Stacks startup hook. It is deliberately
# idempotent because clabgate can also invoke it from a postStart hook.
(
    set -eu

    notebook_home="${HOME:-/home/jovyan}"
    settings_dir="${notebook_home}/.jupyter/lab/user-settings/@jupyterlab/translation-extension"
    startup_dir="${notebook_home}/.ipython/profile_default/startup"

    mkdir -p "${settings_dir}" "${startup_dir}"
    printf '%s\n' '{"locale": "ru_RU"}' > \
        "${settings_dir}/plugin.jupyterlab-settings"

    if [ -d /opt/cms-labs/ipython_startup ]; then
        cp -R /opt/cms-labs/ipython_startup/. "${startup_dir}/"
    fi
)
