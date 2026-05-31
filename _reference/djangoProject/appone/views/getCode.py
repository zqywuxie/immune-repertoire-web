'''
发送验证码
'''
from rest_framework.views import APIView
from rest_framework.response import Response
from djangoProject.tools.sendCodeWithEmail import Code
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from appone.result.myResponse import sucessResponse


class getCode(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        Code.send_email(email)
        return sucessResponse(msg='发送成功')
