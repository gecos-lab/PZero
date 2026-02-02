from abc import ABC, abstractmethod, abstractclassmethod, abstractstaticmethod


class BaseIO(ABC):

    def __init__(self, input_file):
        self._input_file: str = input_file
        self._output_file: str = ""
        self._curr_obj = None

    @property
    def input_file(self) -> str:
        return self._input_file

    @property
    def output_file(self) -> str:
        return self._output_file

    @output_file.setter
    def output_file(self, output_file: str):
        self._output_file = output_file

    @abstractmethod
    def import_from_file(self):
        pass

    @abstractmethod
    def output_to_file(self):
        pass
