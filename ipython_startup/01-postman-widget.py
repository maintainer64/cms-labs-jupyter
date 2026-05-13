from collections import OrderedDict

import ipywidgets as widgets
from IPython.display import display, HTML
from IPython.core.magic import (
    magics_class,
    line_magic,
    Magics,
)
import requests
import json
import time
import xmltodict
from pygments import highlight as pygments_highlight
from pygments.lexers import JsonLexer, XmlLexer, TextLexer
from pygments.formatters import HtmlFormatter
import base64


class PostmanWidget:
    """Виджет API-клиента в стиле Postman для Jupyter."""

    # --- Стили (лёгкая тема, всё с префиксом pmw-) ---
    CSS = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');

        .pmw-container {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #ffffff;
            color: #0f172a;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            max-width: 1100px;
            border: 1px solid #e2e8f0;
            margin: 20px 0;
            box-sizing: border-box;
        }

        .pmw-input-group {
            display: flex !important;
            flex-direction: row !important;
            align-items: stretch !important;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            overflow: hidden;
            background: #fff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
            margin-bottom: 20px;
            padding: 0 !important;
            width: 100%;
        }
        .pmw-input-group:focus-within {
            border-color: var(--jp-brand-color1);
        }

        .pmw-input-group > .widget-dropdown,
        .pmw-input-group > .widget-text,
        .pmw-input-group > .widget-button {
            margin: 0 !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
            min-height: 0 !important;
        }
        .pmw-input-group > .widget-text { flex: 1 1 auto !important; }

        .pmw-method select {
            height: 48px !important;
            min-width: 110px !important;
            background: #f8fafc !important;
            color: #0f172a !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            font-family: 'Inter', sans-serif !important;
            border: none !important;
            border-right: 1px solid #e2e8f0 !important;
            border-radius: 0 !important;
            padding: 0 14px !important;
            cursor: pointer !important;
            outline: none !important;
            appearance: none !important;
            -webkit-appearance: none !important;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'></polyline></svg>") !important;
            background-repeat: no-repeat !important;
            background-position: right 12px center !important;
            padding-right: 32px !important;
        }

        .pmw-url input {
            height: 48px !important;
            background: #ffffff !important;
            color: #0f172a !important;
            font-family: 'Fira Code', monospace !important;
            font-size: 13.5px !important;
            border: none !important;
            border-radius: 0 !important;
            padding: 0 16px !important;
            flex: 1 !important;
            width: 100% !important;
            outline: none !important;
            box-shadow: none !important;
        }
        .pmw-url input::placeholder { color: #94a3b8; }

        .pmw-send button {
            height: 48px !important;
            background: var(--jp-brand-color1) !important;
            color: var(--fill-color, #ffffff) !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            font-family: 'Inter', sans-serif !important;
            letter-spacing: 0.5px !important;
            text-transform: uppercase !important;
            border: none !important;
            border-radius: 0 8px 8px 0 !important;    
            padding: 0 28px !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
            margin: 0 !important;
            min-width: 100px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: filter 0.2s ease, transform 0.1s ease, box-shadow 0.2s ease !important;
        }
        .pmw-send button:hover {
            filter: brightness(1.08);
            box-shadow: 0 2px 6px rgba(0,0,0,0.18) !important;
        }
        .pmw-send button:active {
            filter: brightness(0.92);
            transform: translateY(1px);
            box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
        }

        /* === TABS === */
        .pmw-tabs > .p-TabBar,
        .pmw-tabs > .lm-TabBar {
            background: transparent !important;
            padding: 0 !important;
            margin-bottom: 0 !important;
            min-height: 40px !important;
        }
        .pmw-tabs .p-TabBar-tab,
        .pmw-tabs .lm-TabBar-tab {
            background: transparent !important;
            color: #64748b !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            font-family: 'Inter', sans-serif !important;
            border: none !important;
            border-bottom: 2px solid transparent !important;
            border-radius: 0 !important;
            padding: 10px 18px !important;
            margin: 0 4px 0 0 !important;
            transition: color 0.15s, border-color 0.15s !important;
            min-height: 38px !important;
            box-shadow: none !important;
        }
        .pmw-tabs .p-TabBar-tab.p-mod-current,
        .pmw-tabs .lm-TabBar-tab.lm-mod-current {
            color: var(--jp-brand-color1) !important;
            background: transparent !important;
        }
        .pmw-tabs .p-TabBar-tab:hover:not(.p-mod-current),
        .pmw-tabs .lm-TabBar-tab:hover:not(.lm-mod-current) {
            color: #0f172a !important;
        }
        .pmw-tabs .widget-tab-contents {
            padding: 16px 0 0 0 !important;
            border: none !important;
            background: transparent !important;
        }

        .pmw-textarea textarea {
            background: #f8fafc !important;
            color: #334155 !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 10px !important;
            font-family: 'Fira Code', monospace !important;
            font-size: 13px !important;
            padding: 14px 16px !important;
            line-height: 1.6 !important;
            width: 100% !important;
            box-sizing: border-box !important;
            resize: vertical !important;
            min-height: 180px !important;
            margin: 0 !important;
            transition: border-color 0.2s, box-shadow 0.2s, background 0.2s !important;
        }
        .pmw-textarea textarea:focus {
            background: #ffffff !important;
            border-color: var(--jp-brand-color1) !important;
            outline: none !important;
        }
        .pmw-textarea textarea::placeholder { color: #94a3b8; }

        /* === Auth section === */
        .pmw-section {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 16px;
        }

        .pmw-label {
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: #475569;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .pmw-input input,
        .pmw-password input,
        .pmw-select select {
            width: 100% !important;
            height: 40px !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 8px !important;
            padding: 0 12px !important;
            font-size: 13px !important;
            font-family: 'Inter', sans-serif !important;
            color: #0f172a !important;
            transition: border-color 0.2s, box-shadow 0.2s !important;
            box-sizing: border-box !important;
        }

        .pmw-input input:focus,
        .pmw-password input:focus,
        .pmw-select select:focus {
            border-color: var(--jp-brand-color1) !important;
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
        }

        .pmw-select select {
            cursor: pointer !important;
            appearance: none !important;
            -webkit-appearance: none !important;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'></polyline></svg>") !important;
            background-repeat: no-repeat !important;
            background-position: right 12px center !important;
            padding-right: 32px !important;
        }

        .pmw-form-group {
            margin-top: 14px;
        }

        .pmw-response {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            margin-top: 24px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            animation: pmw-fadeIn 0.35s ease-out;
        }
        @keyframes pmw-fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        .pmw-resp-header {
            background: linear-gradient(180deg, #fafbfc 0%, #f8fafc 100%);
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #e2e8f0;
            flex-wrap: wrap;
            gap: 10px;
        }
        .pmw-resp-header-left {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .pmw-type-tag {
            color: #64748b;
            font-size: 11px;
            font-weight: 700;
            font-family: 'Fira Code', monospace;
            letter-spacing: 0.5px;
            background: #f1f5f9;
            padding: 4px 10px;
            border-radius: 5px;
            border: 1px solid #e2e8f0;
        }
        .pmw-badge {
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            font-family: 'Fira Code', monospace;
            letter-spacing: 0.4px;
        }
        .pmw-badge-2xx { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .pmw-badge-3xx { background: #fef9c3; color: #854d0e; border: 1px solid #fef08a; }
        .pmw-badge-4xx { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .pmw-badge-5xx { background: #fee2e2; color: #7f1d1d; border: 1px solid #fecaca; }
        .pmw-badge-err { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

        .pmw-resp-meta {
            display: flex;
            gap: 14px;
            font-size: 12px;
            color: #64748b;
            font-weight: 600;
        }
        .pmw-resp-meta span {
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .pmw-resp-body {
            padding: 18px 20px;
            overflow: auto;
            max-height: 600px;
            background: #ffffff;
        }
        .pmw-resp-body pre {
            margin: 0 !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            font-family: 'Fira Code', monospace !important;
            font-size: 13px !important;
            line-height: 1.6 !important;
            background: transparent !important;
        }

        .pmw-error {
            color: #991b1b;
            background: #fef2f2;
            border: 1px solid #fecaca;
            padding: 14px 18px;
            border-radius: 10px;
            font-size: 13.5px;
            font-weight: 500;
            margin-top: 20px;
            font-family: 'Inter', sans-serif;
        }
    </style>
    """

    def __init__(self, initial_url=''):
        """Создаёт виджет и настраивает все элементы."""
        self.initial_url = initial_url
        self._build_ui()
        self._wire_events()

    # ------------------------------------------------------------------
    # Внутренние помощники
    # ------------------------------------------------------------------
    @staticmethod
    def _pretty_highlight(content, content_type=''):
        """Форматирует и подсвечивает тело ответа."""
        content_type = content_type.lower()
        formatter = HtmlFormatter(style='xcode', noclasses=True)
        content_str = content if isinstance(content, str) else str(content)
        stripped = content_str.strip()

        # JSON
        if 'json' in content_type or stripped.startswith(('{', '[')):
            try:
                data = json.loads(stripped)
                formatted = json.dumps(data, indent=2, ensure_ascii=False)
                return pygments_highlight(formatted, JsonLexer(), formatter), 'json', '{ }'
            except Exception:
                pass

        # XML / HTML
        if 'xml' in content_type or 'html' in content_type or stripped.startswith('<'):
            try:
                parsed = xmltodict.parse(stripped)
                formatted = xmltodict.unparse(parsed, pretty=True, indent='  ')
                return pygments_highlight(formatted, XmlLexer(), formatter), 'xml', '< >'
            except Exception:
                try:
                    return pygments_highlight(stripped, XmlLexer(), formatter), 'xml', '< >'
                except Exception:
                    pass

        return pygments_highlight(stripped, TextLexer(), formatter), 'text', 'TXT'

    @staticmethod
    def _status_class(code):
        """Возвращает CSS‑класс для бейджа статуса."""
        if 200 <= code < 300: return '2xx'
        if 300 <= code < 400: return '3xx'
        if 400 <= code < 500: return '4xx'
        return '5xx'

    # ------------------------------------------------------------------
    # Сборка интерфейса
    # ------------------------------------------------------------------
    def _build_ui(self):
        """Создаёт все виджеты и укладывает их в контейнер."""
        # Основные элементы
        self.method = widgets.Dropdown(
            options=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
            value='GET',
            layout=widgets.Layout(width='auto', flex='0 0 auto')
        )
        self.method.add_class('pmw-method')

        self.url = widgets.Text(
            value=self.initial_url,
            placeholder='https://api.example.com/v1/resource',
            layout=widgets.Layout(flex='1 1 auto', width='auto')
        )
        self.url.add_class('pmw-url')

        self.send_btn = widgets.Button(
            description='Send',
            layout=widgets.Layout(width='auto', flex='0 0 auto')
        )
        self.send_btn_div = widgets.Box([self.send_btn])
        self.send_btn_div.add_class('pmw-send')

        # === Authorization Tab ===
        self.auth_type = widgets.Dropdown(
            options=['No Auth', 'Bearer Token', 'Basic Auth'],
            value='No Auth',
            layout=widgets.Layout(width='100%')
        )
        self.auth_type.add_class('pmw-select')

        self.bearer_token = widgets.Text(
            placeholder='your-token-here',
            layout=widgets.Layout(width='100%')
        )
        self.bearer_token.add_class('pmw-input')

        self.basic_username = widgets.Text(
            placeholder='username',
            layout=widgets.Layout(width='100%')
        )
        self.basic_username.add_class('pmw-input')

        self.basic_password = widgets.Password(
            placeholder='password',
            layout=widgets.Layout(width='100%')
        )
        self.basic_password.add_class('pmw-password')

        # Контейнеры для разных типов авторизации
        self.bearer_container = widgets.VBox([
            widgets.HTML('<div class="pmw-form-group"></div>'),
            widgets.HTML('<div class="pmw-label">Token</div>'),
            self.bearer_token
        ], layout=widgets.Layout(display='none'))

        self.basic_container = widgets.VBox([
            widgets.HTML('<div class="pmw-form-group"></div>'),  # Отступ сверху
            widgets.HTML('<div class="pmw-label">Username</div>'),
            self.basic_username,
            widgets.HTML('<div class="pmw-label" style="margin-top: 12px;">Password</div>'),
            self.basic_password
        ], layout=widgets.Layout(display='none'))

        self.auth_fields = widgets.VBox([
            self.bearer_container,
            self.basic_container
        ])

        auth_section = widgets.VBox([
            widgets.HTML('<div class="pmw-label">Type</div>'),
            self.auth_type,
            self.auth_fields
        ])
        auth_section.add_class('pmw-section')

        # === Headers Tab ===
        self.headers_input = widgets.Textarea(
            placeholder='{\n  "X-Custom-Header": "value",\n  "Accept": "application/json"\n}',
            layout=widgets.Layout(width='100%')
        )
        self.headers_input.add_class('pmw-textarea')

        # === Body Tab ===
        self.body_input = widgets.Textarea(
            placeholder='JSON | XML | HTML | TEXT',
            layout=widgets.Layout(width='100%')
        )
        self.body_input.add_class('pmw-textarea')

        # Вкладки: Authorization → Headers → Body
        self.tabs = widgets.Tab()
        self.tabs.children = [self.body_input, auth_section, self.headers_input]
        self.tabs.set_title(0, 'Body')
        self.tabs.set_title(1, 'Authorization')
        self.tabs.set_title(2, 'Headers')
        self.tabs.add_class('pmw-tabs')

        self.output = widgets.Output()

        # Объединяем метод + url + кнопку в строку
        url_bar = widgets.HBox(
            [self.method, self.url, self.send_btn_div],
            layout=widgets.Layout(width='100%', align_items='stretch')
        )
        url_bar.add_class('pmw-input-group')

        # Главный контейнер
        self.container = widgets.VBox(
            [url_bar, self.tabs, self.output],
            layout=widgets.Layout(width='100%')
        )
        self.container.add_class('pmw-container')

    def _wire_events(self):
        """Привязывает обработчики событий."""
        self.send_btn.on_click(self._on_send_click)
        self.auth_type.observe(self._on_auth_type_change, names='value')

    def _on_auth_type_change(self, change):
        """Показывает/скрывает поля авторизации в зависимости от типа."""
        auth_type = change['new']

        if auth_type == 'Bearer Token':
            self.bearer_container.layout.display = 'block'
            self.basic_container.layout.display = 'none'
        elif auth_type == 'Basic Auth':
            self.bearer_container.layout.display = 'none'
            self.basic_container.layout.display = 'block'
        else:  # No Auth
            self.bearer_container.layout.display = 'none'
            self.basic_container.layout.display = 'none'

    # ------------------------------------------------------------------
    # Логика отправки запроса
    # ------------------------------------------------------------------
    def _prepare_headers(self):
        """Подготавливает заголовки с учетом авторизации."""
        # Начинаем с пользовательских заголовков
        h_str = self.headers_input.value.strip()
        headers_dict = json.loads(h_str) if h_str else {}

        # Добавляем авторизацию (если не переопределена в Headers)
        auth_type = self.auth_type.value

        if auth_type == 'Bearer Token' and 'Authorization' not in headers_dict:
            token = self.bearer_token.value.strip()
            if token:
                headers_dict['Authorization'] = f'Bearer {token}'

        elif auth_type == 'Basic Auth' and 'Authorization' not in headers_dict:
            username = self.basic_username.value.strip()
            password = self.basic_password.value.strip()
            if username or password:
                credentials = f'{username}:{password}'
                encoded = base64.b64encode(credentials.encode()).decode()
                headers_dict['Authorization'] = f'Basic {encoded}'

        return headers_dict

    def _on_send_click(self, _):
        """Обработчик клика по кнопке Send."""
        self.output.clear_output()
        with self.output:
            try:
                # Подготавливаем заголовки (с авторизацией)
                headers_dict = self._prepare_headers()

                # Подготавливаем тело
                b_str = self.body_input.value.strip()
                body_data = b_str
                if b_str:
                    if b_str.startswith(('{', '[')):
                        try:
                            parsed = json.loads(b_str)
                            body_data = json.dumps(parsed, indent=2, ensure_ascii=False)
                            self.body_input.value = body_data
                            if 'Content-Type' not in headers_dict:
                                headers_dict['Content-Type'] = 'application/json'
                        except Exception:
                            pass
                    elif b_str.startswith('<'):
                        try:
                            parsed = xmltodict.parse(b_str)
                            body_data = xmltodict.unparse(parsed, pretty=True, indent='  ')
                            self.body_input.value = body_data
                            if 'Content-Type' not in headers_dict:
                                headers_dict['Content-Type'] = 'application/xml'
                        except Exception:
                            pass

                start = time.time()
                resp = requests.request(
                    self.method.value,
                    self.url.value,
                    headers=headers_dict,
                    data=body_data if isinstance(body_data, str) else None,
                    json=body_data if isinstance(body_data, (dict, list)) else None,
                    verify=False,  # SSL проверка отключена
                    timeout=20
                )
                ms = round((time.time() - start) * 1000)

                high, r_type, icon = self._pretty_highlight(
                    resp.text, resp.headers.get('Content-Type', '')
                )
                status_cls = self._status_class(resp.status_code)

                size_bytes = len(resp.content)
                size_str = f"{size_bytes} B" if size_bytes < 1024 else f"{size_bytes / 1024:.1f} KB"

                display(HTML(f"""
                <div class="pmw-response">
                    <div class="pmw-resp-header">
                        <div class="pmw-resp-header-left">
                            <span class="pmw-badge pmw-badge-{status_cls}">{resp.status_code} {resp.reason}</span>
                            <span class="pmw-type-tag">{icon} {r_type.upper()}</span>
                        </div>
                        <div class="pmw-resp-meta">
                            <span>⏱ {ms} ms</span>
                            <span>📦 {size_str}</span>
                        </div>
                    </div>
                    <div class="pmw-resp-body">{high}</div>
                </div>
                """))

            except requests.exceptions.RequestException as e:
                display(HTML(f'<div class="pmw-error">⚠️ Network Error: {str(e)}</div>'))
            except Exception as e:
                display(HTML(f'<div class="pmw-error">⚠️ Error: {str(e)}</div>'))

    # ------------------------------------------------------------------
    # Публичный метод отображения
    # ------------------------------------------------------------------
    def display(self):
        """Показывает виджет в Jupyter (всегда вставляет CSS)."""
        display(HTML(self.CSS))  # Всегда отображаем CSS
        display(self.container)

    def close(self):
        """Закрывает виджет."""
        self.container.close()


@magics_class
class PostmanMagic(Magics):
    """IPython magic для создания PostmanWidget."""

    # Хранилище активных виджетов (OrderedDict для LRU)
    _max_instances = 10
    _instances = OrderedDict()  # {url: widget}

    @line_magic
    def postman(self, line):
        """
        Создаёт новый экземпляр PostmanWidget или возвращает существующий.
        Если URL совпадает с уже открытым виджетом, возвращает его.
        Хранится максимум 100 виджетов, старые автоматически удаляются.

        Использование:
            %postman                              # пустой виджет
            %postman https://api.example.com      # с предзаполненным URL (переиспользуется если уже открыт)
        """
        url = line.strip() if line else ''

        # Проверяем, есть ли уже виджет с таким URL
        if url in PostmanMagic._instances:
            widget = PostmanMagic._instances[url]
            # Перемещаем в конец (LRU - недавно использованный)
            PostmanMagic._instances.move_to_end(url)
            # Показываем существующий виджет
            widget.display()
            return

        # Если достигли лимита, удаляем самый старый (первый)
        if len(PostmanMagic._instances) >= self._max_instances:
            oldest_url, old_widget = PostmanMagic._instances.popitem(last=False)
            try:
                old_widget.close()
            except:
                pass

        # Создаём новый виджет
        widget = PostmanWidget(initial_url=url)

        # Добавляем в хранилище (в конец)
        PostmanMagic._instances[url] = widget

        # Показываем
        widget.display()


# Регистрируем magic
get_ipython().register_magics(PostmanMagic)
