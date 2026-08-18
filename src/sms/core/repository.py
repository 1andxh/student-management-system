from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    """Persistence contract for one aggregate root. Method names are
    domain-meaningful (a repository's job is "persist/retrieve this
    aggregate", not "run this query") so each concrete domain repository
    typically adds more specific lookups (e.g. get_by_email) alongside
    these. Swapping in an in-memory fake of this for service-level unit
    tests is the point of the abstraction."""

    @abstractmethod
    async def add(self, entity: T) -> T: ...

    @abstractmethod
    async def get(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    async def list(self) -> list[T]: ...

    @abstractmethod
    async def remove(self, entity: T) -> None: ...
