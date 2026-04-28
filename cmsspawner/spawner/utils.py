import logging
import os

from jinja2 import FileSystemLoader, Environment


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


async def render_template(template_name: str, **kwargs) -> str:
    """
    Рендеринг шаблона формы.
    :param template_name: Имя формы
    :param kwargs: Параметры для рендеринга шаблона
    :return:
    """
    template_path = os.path.join(os.path.dirname(__file__), '../templates')
    template_loader = FileSystemLoader(searchpath=template_path)
    template_env = Environment(loader=template_loader, enable_async=True)
    template = template_env.get_template(name=template_name)
    rendered_code = await template.render_async(**kwargs)
    return rendered_code
