from abc import ABC, abstractmethod
from typing import Optional, List


class ConsoleOutput:
    def __init__(self, stdout=None, stderr=None):
        self._stdout = stdout
        self._stderr = stderr

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def __str__(self):
        return f"stdout: {self.stdout} \nstderr: {self.stderr}"

class KubernetesConsoleOutput(ConsoleOutput):
    def __init__(self, exit_code: int, text: str):
        super().__init__(text)
        self.exit_code = exit_code

    def __str__(self):
        return f"KubernetesConsoleOutput(text={self.text}, exit_code={self.exit_code})"


class Session(ABC):
    def __init__(self, lang: str, verbose: bool = True, *args, **kwargs):
        self.lang = lang
        self.verbose = verbose
        super().__init__(*args, **kwargs)

    @abstractmethod
    def open(self):
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError

    @abstractmethod
    def run(self, code: str, libraries: Optional[List] = None) -> ConsoleOutput:
        raise NotImplementedError

    @abstractmethod
    def copy_to_runtime(self, src: str, dest: str):
        raise NotImplementedError

    @abstractmethod
    def copy_from_runtime(self, src: str, dest: str):
        raise NotImplementedError

    @abstractmethod
    def execute_command(self, command: str):
        raise NotImplementedError

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()
