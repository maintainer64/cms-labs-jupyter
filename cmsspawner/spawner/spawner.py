import logging

from tornado import web

from kubespawner import KubeSpawner
from .utils import setup_logger


class CMSSpawner(KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(__name__, logging.INFO)
        self.logger.info('Start working with CMSSpawner')

    async def _start(self):
        if not self.name:
            self.log.warning(f"User {self.user.name} tried to launch a nameless default server.")
            raise web.HTTPError(
                400,
                "Запуск стандартного сервера запрещен. Пожалуйста, используйте ссылки из Moodle для запуска лабораторных работ."
            )
        if self.extra_labels is None:
            self.extra_labels = {}
        if self.user_options and 'profile' in self.user_options:
            attempt_id = str(self.user_options['profile'])
            self.extra_labels.update({
                "hub.jupyter.org/cms_attempt_id": attempt_id,
            })
            self.env['ATTEMPT_ID'] = attempt_id
            self.log.info(f"Updated extra_labels with attempt_id: {attempt_id}")
        return await super()._start()