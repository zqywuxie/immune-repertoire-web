from rest_framework.response import Response


class sucessResponse(Response):
    def __init__(self, data=None, msg="success", status=None,
                 template_name=None, headers=None,
                 exception=False, content_type=None):
        result = {'code': 200, 'msg': msg, 'data': data}
        super().__init__(result, status, template_name, headers,
                         exception, content_type)


class failResponse(Response):
    def __init__(self, data=None, msg="fail", code=400, status=None,
                 template_name=None, headers=None,
                 exception=False, content_type=None):
        result = {'code': code, 'msg': msg, 'data': data}
        super().__init__(result, status, template_name, headers,
                         exception, content_type)


class pageResponse(Response):
    def __init__(self, data=None, msg='success', status=None, template_name=None, headers=None, exception=False,
                 content_type=None, page=1, limit=1, total=1):
        std_data = {
            "code": 200,
            "data": {
                "page": page,
                "limit": limit,
                "total": total,
                "data": data
            },
            "msg": msg
        }
        super().__init__(std_data, status, template_name, headers, exception, content_type)
