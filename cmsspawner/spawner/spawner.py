import logging

from kubespawner import KubeSpawner

from .utils import setup_logger


class CMSSpawner(KubeSpawner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = setup_logger(__name__, logging.ERROR)
        self.logger.info('Start working with CMSSpawner')
