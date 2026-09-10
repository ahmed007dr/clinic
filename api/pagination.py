"""Paging that a table component can drive directly.

DRF's default returns `next`/`previous` as absolute URLs, which is fine for a
browsable API and awkward for a React table that wants to render page numbers.
This adds the two numbers the UI actually needs so the client never has to
parse a URL to know where it is.
"""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ClinicPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    # A ceiling, so a client cannot ask for a whole clinic's history in one
    # response and turn a list endpoint into an export.
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("pages", self.page.paginator.num_pages),
                    ("page_size", self.get_page_size(self.request)),
                    ("results", data),
                ]
            )
        )
