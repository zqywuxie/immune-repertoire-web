from django.db import models
from django.contrib.auth.models import User


class EmailCode(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=20)
    create_time = models.DateTimeField(verbose_name='创建时间',auto_now_add=True)

    class Meta:
        verbose_name = '邮箱验证码'
        verbose_name_plural = verbose_name
