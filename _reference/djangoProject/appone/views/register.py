from datetime import datetime, timedelta

from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from djangoProject.tools.sendCodeWithEmail import Code
from appone.models.EmailCode import EmailCode
from appone.models.UserInfo import UserInfo
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny ,IsAuthenticated
from django.utils import timezone
from appone.result.myResponse import *
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email')
        code = request.data.get('code')
        # 验证邮箱和用户名是否存在
        if not all([username, password, email, code]):
            return failResponse(msg='缺少参数')

        user = UserInfo.objects.filter(username=username).first()
        user_email = UserInfo.objects.filter(email=email).first()
        if user or user_email:
            return failResponse(msg='用户名或邮箱已存在')
        log_code = EmailCode.objects.filter(email=email).order_by('-create_time')
        if log_code:
            newly_code = log_code[0]
            time = timezone.now() - timedelta(hours=0, minutes=5, seconds=0)
            print("当前时间减去5分钟：",time)
            print("最新验证码的时间",newly_code.create_time)
            if newly_code.create_time >= time:
                if newly_code.code == code:
                    user = User.objects.create_user(username=username, password=password, email=email)
                    UserInfo.objects.create(user=user, username=username, email=email,
                                            user_id=user.id)
                    return sucessResponse(msg='注册成功')
                else:
                    return failResponse(msg='验证码错误')
            else:
                return failResponse(msg='验证码过期')
        else:
            return failResponse(msg='未知错误')
