# agents/base.py
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    name: str

    @abstractmethod
    def handle(self, **kwargs) -> dict:
        """
        处理函数，根据kwargs中的信息进行处理，返回结果
        :param kwargs:
        :return:
        """



        pass