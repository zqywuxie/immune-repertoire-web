from django.db import models
from django.contrib.auth.models import User


class UserInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    username = models.CharField(max_length=20, verbose_name='用户名')
    creat_time = models.DateTimeField(auto_now_add=True ,verbose_name='创建时间')
    age = models.IntegerField(verbose_name='年龄')
    email = models.EmailField(verbose_name='邮箱')
    class Meta:
        verbose_name = '用户信息'
        verbose_name_plural = verbose_name
