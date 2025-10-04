
from dataclasses import dataclass
from typing import Any

class Result[S, E]:
	...

@dataclass
class Ok[S](Result[S, Any]):
	value: S

@dataclass
class Error[E](Result[Any, E]):
	error: E
