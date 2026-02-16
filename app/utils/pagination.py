# app/utils/pagination.py — Pagination helpers

from pydantic import BaseModel


class PaginationParams(BaseModel):
    page: int = 1
    per_page: int = 50

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


class PaginatedResponse(BaseModel):
    data: list
    total: int
    page: int
    per_page: int
    total_pages: int

    @classmethod
    def create(
        cls,
        data: list,
        total: int,
        pagination: PaginationParams,
    ) -> "PaginatedResponse":
        total_pages = (total + pagination.per_page - 1) // pagination.per_page
        return cls(
            data=data,
            total=total,
            page=pagination.page,
            per_page=pagination.per_page,
            total_pages=total_pages,
        )
