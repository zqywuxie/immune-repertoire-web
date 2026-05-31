from django.urls import path

from appone.views.Login import LoginView ,LoginOutView
from appone.views.register import RegisterView
from appone.views.getCode import getCode
from appone.tests import Test
from appone.views.appProject import addProject,addDatapoint,addPep,addGroupSpecification,insert_sample_Summary_Table

from appone.views.project import ProjectView, download_processed_file
from appone.views.sample_browser import (page_research, download_research_data, get_field_list_by_parm,
                                         edit_sample_data, download_standard_sample_table)

urlpatterns = [
    #path("api/appone/login/", LoginView.as_view(), name="login"),

    path("test",Test.as_view()),
    path("user/login/", LoginView.as_view(), name="login"),
    path("user/register/", RegisterView.as_view(), name="register"),
    path("user/loginOut/", LoginOutView.as_view(), name="loginOut"),
    path("user/getCode/", getCode.as_view(), name="获取验证码"),
    # path("uploadFile/", files.as_view(), name="上传文件"),

    path("addProject/", addProject.as_view(), name="添加项目"),
    path("addDatapoint/", addDatapoint.as_view(), name="样品说明文件"),
    path("addGroupSpecification/", addGroupSpecification.as_view(), name="分组说明文件"),
    path("addPep/", addPep.as_view(), name="pep文件"),
    path("addSampleSummaryTable/", insert_sample_Summary_Table),

    path("project/", ProjectView.as_view(), name="项目管理"),
    path("downloadprocessfile/", download_processed_file),


    path("pageresearch/", page_research),
    path("downloadresearchdata/", download_research_data),
    path("get_field_list_by_parm/", get_field_list_by_parm),
    path("edit_sample_data/", edit_sample_data),
    path("downloadsamplefile/", download_standard_sample_table),

    #





]