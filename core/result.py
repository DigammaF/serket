
from dataclasses import dataclass
from typing import Any, Callable

class Result[S, E]:
	def unwrap_or(self, default_factory: Callable[[], S]) -> S: ...

@dataclass
class Ok[S](Result[S, Any]):
	value: S

	def unwrap_or(self, default_factory: Callable[[], S]) -> S:
		return self.value

@dataclass
class Error[E](Result[Any, E]):
	error: E

	def unwrap_or(self, default_factory: Callable[[], Any]) -> Any:
		return default_factory()
