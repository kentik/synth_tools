from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class KentikAPIRequestError(Exception):
    def __init__(self, status: int, message: str, response):
        self.status = status
        self.message = message
        self.response = response

    def __repr__(self):
        return f"APIRequestError:{self.message}"

    def __str__(self):
        return f"{self.message}"


class KentikAPITransport(ABC):
    @abstractmethod
    def __init__(self, credentials: Tuple[str, str], url: str):
        raise NotImplementedError

    @abstractmethod
    def req(self, op: str, **kwargs) -> Any:
        return NotImplementedError
