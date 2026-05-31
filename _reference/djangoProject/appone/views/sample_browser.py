import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from django.http import FileResponse
#from drf_yasg.utils import swagger_auto_schema
from pymongo import MongoClient
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from appone.constant import DBURL, PROJECT_DB_NAME, PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME, PROJECT_FILE, \
    PROJECT_COLLECTION_NAME
from appone.result.myResponse import failResponse, pageResponse, sucessResponse
import pandas as pd
from djangoProject.tools.logger import log

logger = log.GetLogger().get_logger()


# 分页查询 下载

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def page_research(request):
    user_id = str(request.user.id)
    page = int(request.data.get("pageNum"))
    size = int(request.data.get("pageSize"))
    sampleId = request.data.get("id")
    name = request.data.get("name")
    project_name = request.data.get("project_name")
    institution = request.data.get("institution")
    spices = request.data.get("spices")
    illness = request.data.get("illness")
    iso_tag = request.data.get("iso_tag")
    is_healthy = request.data.get("is_healthy")
    chain_flag = request.data.get("chain_flag")
    is_Pe = request.data.get("is_Pe")
    contain_method = request.data.get("contain_method")

    param_dict = get_query_dict(institution=institution, spices=spices, illness=illness)
    like_param_dict = get_like_query_dict(id=sampleId, name=name, project_name=project_name, iso_tag=iso_tag,
                                          contain_method=contain_method)
    int_parm_dict = get_int_query_dict(is_healthy=is_healthy, chain_flag=chain_flag, is_Pe=is_Pe)
    # print(like_param_dict)
    query_dict = {"$and": []}
    query_dict_0 = {}
    if param_dict:
        for key, value in param_dict.items():
            # print(type(value), value)
            query_dict_0[key] = value.split(",")
    if like_param_dict:
        for key, value in like_param_dict.items():
            query_dict_0[key] = [re.compile('.*' + re.escape(value) + '.*', re.IGNORECASE)]
    if query_dict_0:
        for key, value in query_dict_0.items():
            query_dict["$and"].append({key: {"$in": value}})
    if int_parm_dict:
        for key, value in int_parm_dict.items():
            query_dict["$and"].append({key: {"$in": [value]}})
    if len(query_dict["$and"]) == 0:
        query_dict = {}
    print(query_dict)
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[PROJECT_DB_NAME]
        sample_collection = db[PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME]
        # total = sample_collection.count_documents({})
        total = sample_collection.count_documents(query_dict)
        datas = sample_collection.find(query_dict, {"_id": 0}).skip((page - 1) * size).limit(size).sort("create_time",
                                                                                                         -1)
        data = [i for i in datas]
        for i in data:
            if "is_healthy" in i:
                i["is_healthy"] = "是" if i["is_healthy"] == 1 else "否"
            if "is_Pe" in i :
                i["is_Pe"] = "是" if i["is_Pe"] == 1 else "否"
        print(data)
        return pageResponse(data=data, page=page, limit=size, total=total)
    except Exception as e:
        print(e)
        return failResponse(msg=f"{e}")
    finally:
        client.close()


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def download_research_data(request):
    user_id = str(request.user.id)
    sampleId = request.data.get("id")
    name = request.data.get("name")
    project_name = request.data.get("project_name")
    institution = request.data.get("institution")
    spices = request.data.get("spices")
    illness = request.data.get("illness")
    iso_tag = request.data.get("iso_tag")
    is_healthy = request.data.get("is_healthy")
    chain_flag = request.data.get("chain_flag")
    is_Pe = request.data.get("is_Pe")
    contain_method = request.data.get("contain_method")
    param_dict = get_query_dict(institution=institution, spices=spices, illness=illness)
    like_param_dict = get_like_query_dict(id=sampleId, name=name, project_name=project_name, iso_tag=iso_tag,
                                          contain_method=contain_method)
    int_parm_dict = get_int_query_dict(is_healthy=is_healthy, chain_flag=chain_flag, is_Pe=is_Pe)
    print(like_param_dict)
    query_dict = {"$and": []}
    query_dict_0 = {}
    if param_dict:
        for key, value in param_dict.items():
            print(type(value), value)
            query_dict_0[key] = value.split(",")
    if like_param_dict:
        for key, value in like_param_dict.items():
            query_dict_0[key] = [re.compile('.*' + re.escape(value) + '.*', re.IGNORECASE)]
    if query_dict_0:
        for key, value in query_dict_0.items():
            query_dict["$and"].append({key: {"$in": value}})
    if int_parm_dict:
        for key, value in int_parm_dict.items():
            query_dict["$and"].append({key: {"$in": [value]}})
    if len(query_dict["$and"]) == 0:
        query_dict = {}
    print(query_dict)
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[PROJECT_DB_NAME]
        sample_collection = db[PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME]
        df = pd.DataFrame(list(
            sample_collection.find(query_dict, {"_id": 0, "id": 0}).sort("create_time", -1)))
        datapoint_df = pd.DataFrame()
        save_path = str(uuid.uuid4()).replace("-", "")
        for index, row in df.iterrows():
            project_name = row["project_name"]
            name = row["name"]
            project_db = client[project_name]
            collection_names = project_db.list_collection_names()
            datapoint_collection = project_db["datapoint"]
            query_datapoint_df = pd.DataFrame(list(datapoint_collection.find({"sample": name}, {"_id": 0})))
            datapoint_df = pd.concat([datapoint_df, query_datapoint_df])
            for collection_name in collection_names:
                if name in collection_name:
                    datapoint_collection = project_db[collection_name]
                    df = pd.DataFrame(list(datapoint_collection.find({}, {"_id": 0})))
                    check_dir(f"{PROJECT_FILE}/download_file/{save_path}/")
                    df.to_csv(f"{PROJECT_FILE}/download_file/{save_path}/{collection_name}.csv", index=False)
        check_dir(f"{PROJECT_FILE}/download_file/{save_path}/")
        datapoint_df.to_csv(f"{PROJECT_FILE}/download_file/{save_path}/datapoint.csv", index=False)
        # to_tar
        target_path = f"{PROJECT_FILE}/download_file/{str(uuid.uuid4()).replace('-', '')}"
        resp = to_make_archive(target_path=target_path, archive_path=f"{PROJECT_FILE}/download_file/{save_path}/")
        # 创建 HTTP 响应对象
        # response = sucessResponse(data=csv_data, content_type="text/csv")
        # response["Content-Disposition"] = 'attachment; filename="exported_data.csv"'
        return resp
    except Exception as e:
        print(e)
        return failResponse(msg=f"{e}")
    finally:
        client.close()

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def download_standard_sample_table(request):
    from appone.constant import SAMPLE_TABLE
    target_path = f"{PROJECT_FILE}/download_file/{str(uuid.uuid4()).replace('-', '')}"
    resp = to_make_archive(target_path=target_path, archive_path=SAMPLE_TABLE)
    return resp



@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_field_list_by_parm(request):
    parm = request.query_params.get("parm")
    try:
        return_list = []
        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[PROJECT_DB_NAME]
        project_collection = db[PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME]
        illness_list = project_collection.distinct(parm)
        if not illness_list:
            return sucessResponse(data=[])
        if parm == "is_healthy" or parm == "is_Pe":
            for institution in illness_list:
                return_list.append({"value": institution, "label": "是" if institution == "1" or institution == 1 else "否"})
        else:
            for institution in illness_list:
                return_list.append({"value": institution, "label": institution})
        return sucessResponse(data=return_list)
    except Exception as e:
        print(e)
        return failResponse(msg=f"{e}")
    finally:
        client.close()



@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def edit_sample_data(request):
    user = request.user
    sample_dict = request.data
    project_name = sample_dict["project_name"]
    sample_id = sample_dict["id"]
    sample_dict.pop("id")
    sample_dict.pop("project_name")
    print(sample_dict)
    # is your sample here
    client = MongoClient(DBURL, maxidletimems=120000)
    project = client[PROJECT_DB_NAME][PROJECT_COLLECTION_NAME].find_one({"name": project_name})
    if project and str(user.id) == str(project["user_id"]):
        # edit your sample here
        sample_collection = client[PROJECT_DB_NAME][PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME].update_one(
            {"id": sample_id},
            {"$set": sample_dict}
        )
        return sucessResponse()
    else:
        return failResponse(msg="这不是你上传的")


def get_query_dict(**kwargs):
    query_dict = {}
    for key, value in kwargs.items():
        if value and value != "":
            query_dict[key] = value
    return query_dict


def get_like_query_dict(**kwargs):
    like_query_dict = {}
    for key, value in kwargs.items():
        if value and value != "":
            like_query_dict[key] = value
    return like_query_dict


def get_int_query_dict(**kwargs):
    int_query_dict = {}
    for key, value in kwargs.items():
        if value and value != "":
            int_query_dict[key] = int(value)
    return int_query_dict


def check_dir(dirs):
    if not os.path.exists(dirs):
        os.makedirs(dirs)


def to_make_archive(target_path, archive_path):
    # 压缩文件夹
    try:
        zip_file_path = f"{target_path}.zip"
        if os.path.isdir(archive_path):
            # print("压缩文件夹")
            shutil.make_archive(base_name=target_path,format='zip', root_dir=archive_path)
        else:
            # print("压缩文件")
            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                # 获取文件名，避免路径嵌套
                filename = Path(archive_path).name
                zipf.write(archive_path, filename)
    except Exception as e:
        logger.error(f"Error compressing folder: {e}")
        return failResponse(msg="Failed to compress folder", code=500)
    # 构建压缩文件的路径
    zip_file_path = f"{target_path}.zip"
    if not os.path.isfile(zip_file_path):
        logger.error(f"Compressed file '{zip_file_path}' does not exist")
        return failResponse(msg=f"Compressed file '{zip_file_path}' does not exist")

    # 读取压缩文件内容
    try:
        zip_content = open(zip_file_path, 'rb')
        response = FileResponse(zip_content, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(zip_file_path)}"'
    except Exception as e:
        print(e)
        logger.error(f"Error reading compressed file: {e}")
        # return failResponse(msg="Failed to read compressed file")
    return response
