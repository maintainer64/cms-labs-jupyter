import logging


def setup_logger(logger_name, level=logging.INFO):
    """
    Настройка логгера в консоль.
    :param logger_name:
    :param level:
    :return:
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
