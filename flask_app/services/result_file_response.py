"""Preserve Flask file responses while accepting suffix ranges larger than a file."""
from pathlib import Path
from flask import request, send_file
from werkzeug.exceptions import RequestedRangeNotSatisfiable


def send_result_file(path: Path, **options):
    requested = request.range
    try:
        if requested and requested.units == "bytes" and len(requested.ranges) == 1:
            start, end = requested.ranges[0]
            size = path.stat().st_size
            if start < 0 and end is None and -start > size:
                # Werkzeug rejects an oversized suffix instead of clamping its start.
                response = send_file(path, conditional=False, **options)
                if size:
                    environ = dict(request.environ, HTTP_RANGE=f"bytes=0-{size - 1}")
                    response.make_conditional(environ, accept_ranges=True, complete_length=size)
                return response
        return send_file(path, **options)
    except RequestedRangeNotSatisfiable as error:
        return error.get_response()
