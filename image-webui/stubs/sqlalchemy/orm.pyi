from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, Generic, Iterator

T = TypeVar('T')

class Session:
    def __init__(self, **kwargs: Any): ...
    def add(self, instance: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
    def query(self, *entities: Any, **kwargs: Any) -> "Query": ...
    def __enter__(self) -> "Session": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

class Query(Generic[T]):
    def filter(self, *criterion: Any) -> "Query[T]": ...
    def filter_by(self, **kwargs: Any) -> "Query[T]": ...
    def all(self) -> List[T]: ...
    def first(self) -> Optional[T]: ...
    def one(self) -> T: ...
    def one_or_none(self) -> Optional[T]: ...
    def count(self) -> int: ...
    def delete(self) -> int: ...
    def order_by(self, *criterion: Any) -> "Query[T]": ...
    def limit(self, limit: int) -> "Query[T]": ...
    def offset(self, offset: int) -> "Query[T]": ...
    def __iter__(self) -> Iterator[T]: ...
