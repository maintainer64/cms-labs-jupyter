import paramiko
from IPython.core.magic import Magics, magics_class, cell_magic


@magics_class
class SSHMagics(Magics):
    @cell_magic
    def ssh(self, line, cell):
        """
        Использование:
        %%ssh password user@host [port]
        """
        args = line.split()
        if len(args) < 2:
            print("Ошибка! Формат: %%ssh пароль user@host [port]")
            return

        password = args[0]
        user_host = args[1]
        # Если есть третий аргумент — это порт, иначе 22
        port = int(args[2]) if len(args) > 2 else 22

        try:
            if '@' not in user_host:
                print("Ошибка: используйте формат user@host")
                return

            user, host = user_host.split('@')

            client = paramiko.SSHClient()
            # "Force keys": игнорируем проверку и всегда доверяем
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            client.connect(hostname=host, port=port, username=user, password=password, timeout=10)

            # Выполняем всё содержимое ячейки как одну сессию
            stdin, stdout, stderr = client.exec_command(cell)

            out = stdout.read().decode('utf-8', 'ignore').strip()
            err = stderr.read().decode('utf-8', 'ignore').strip()

            if out: print(out)
            if err: print(f"--- LOG/STDERR ---\n{err}")

        except Exception as e:
            print(f"Ошибка: {e}")
        finally:
            client.close()


# Регистрация
get_ipython().register_magics(SSHMagics)
