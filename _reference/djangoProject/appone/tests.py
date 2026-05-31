import os.path

from django.test import TestCase

# Create your tests here.
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from djangoProject.tools.sendCodeWithEmail import Code
from appone.models.EmailCode import EmailCode
from appone.models.UserInfo import UserInfo
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated

#test images
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import uuid
import parmap

from appone.result.myResponse import *


class Test(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        print(request.user)
        print(request.GET)
        print(request.GET.get("萨达"))
        print(type(request.GET.get("萨达")))
        return pageResponse()

    def post(self, request):
        # files = request.FILES.getlist('file')
        # if files:
        #     for f in files:
        #         db = pd.read_csv(f)
        #         print(db)
        print(request.data)
        print(request.data.get("list"))
        print(type(request.data.get("list")))
        # list_1 = request.data.get("list")
        # runtime = parmap.map_async(read, list_1)
        # runtime.wait()
        # result = runtime.get()
        # print(result)
        return sucessResponse()


def read(ele):
    print(ele)
    return ele
