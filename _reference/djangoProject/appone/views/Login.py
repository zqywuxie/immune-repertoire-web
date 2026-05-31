from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from appone.result.myResponse import *

from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()
class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        """
                登录
                :param request:
                :param username: 账号
                :param password: 密码
                :return:
                """
        username = request.data.get('username')
        password = request.data.get('password')
        try:
            user = User.objects.get(username=username)
            if user and user.check_password(password):
                # token, created = Token.objects.get_or_create(user=user)
                token, created = Token.objects.update_or_create(user=user)
                data = {
                    'token': token.key,
                    'username': user.username,
                    "email": user.email,
                    'id': user.id
                }
                logger.info(f"{username}登录成功")
                return sucessResponse(data=data, msg='登录成功')
            else:
                return failResponse(msg='用户名或密码错误')
        except Exception as e:
            return failResponse(msg=f'用户名或密码错误{e}')


class LoginOutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    def get(self, request):
        try:
            logger.info(f"{request.user}退出成功")
            request.user.auth_token.delete()
            return sucessResponse(msg='退出成功')
        except Exception as e:
            return failResponse(msg=f'错误{e}')
