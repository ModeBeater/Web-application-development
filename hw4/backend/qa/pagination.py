"""?limit=&offset= pagination for every list endpoint."""

from rest_framework.pagination import LimitOffsetPagination as DrfLimitOffsetPagination


class LimitOffsetPagination(DrfLimitOffsetPagination):
    """
    GET /api/questions/?limit=20&offset=40 -> {"count": 107, "next": ..., "previous": ..., "results": [...]}

    `count` is the total number of matches, so a client knows how many pages there are.
    Without parameters the first PAGE_SIZE (50) items are returned; the maximum is 500.
    """

    default_limit = 50
    max_limit = 500
    limit_query_param = "limit"
    offset_query_param = "offset"
