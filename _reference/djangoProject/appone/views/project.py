import os.path
import uuid

from django.http import FileResponse
from pymongo import MongoClient
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from appone.result.myResponse import *
import re
from appone.constant import DBURL, CHAIN_TYPES, PROJECT_DB_NAME, PROJECT_COLLECTION_NAME, \
    PROJECT_DATAPOINT_COLLECTION_NAME, PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME, PROJECT_FILE
from appone.views.sample_browser import to_make_archive
from djangoProject.tools.logger import log

logger = log.GetLogger().get_logger()


class ProjectView(APIView):
    """项目管理"""
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    #分页查询
    def get(self, request, ):
        name = request.GET.get("name")
        cor_level = request.GET.get("cooperation_level")
        institution = request.GET.get("institution")
        page = int(request.GET.get("pageNum"))
        size = int(request.GET.get("pageSize"))
        user_id = str(request.user.id)
        try:
            # 连接到MongoDB
            client = MongoClient(DBURL, maxidletimems=120000)
            # 选择数据库
            db = client[PROJECT_DB_NAME]
            collection = db[PROJECT_COLLECTION_NAME]
            # 计算跳过的文档数量
            skip_amount = size * (page - 1)
            query_dict = {}
            if name is not None and name != "":
                name_pattern = re.compile('.*' + re.escape(name) + '.*', re.IGNORECASE)
                query_dict["name"] = name_pattern
            if cor_level is not None and cor_level != "":
                cor_level_pattern = re.compile('.*' + re.escape(cor_level) + '.*', re.IGNORECASE)
                query_dict["cooperation_level"] = cor_level_pattern
            if institution is not None and institution != "":
                institution_pattern = re.compile('.*' + re.escape(institution) + '.*', re.IGNORECASE)
                query_dict["institution"] = institution_pattern
            print(query_dict)
            total = collection.count_documents(query_dict)
            results = collection.find(query_dict).skip(
                skip_amount).limit(size).sort("create_time", -1)
            datas = []
            for i in list(results):
                i.pop("_id")
                i.pop("id")
                i.pop("user_id")
                if i["is_datapoint"] == "True":
                    i["is_datapoint"] = "是"
                else:
                    i["is_datapoint"] = "否"
                if i["is_pep"] == "True":
                    i["is_pep"] = "是"
                else:
                    i["is_pep"] = "否"
                datas.append(i)
            # print('datas:', datas)
            # print(request.user.id)
            return pageResponse(data=datas, page=page, limit=size, total=total)
        except Exception as e:
            print(e)
            return failResponse(msg="查询失败")
        finally:
            client.close()

    # 删除
    seven_chain_list = CHAIN_TYPES

    def delete(self, request):
        user = request.user
        name = str(request.GET.get("name")).strip()
        print("name:", name)
        try:
            client = MongoClient(DBURL, maxidletimems=120000)
            db = client[PROJECT_DB_NAME]
            project_collection = db[PROJECT_COLLECTION_NAME]
            sample_summary = db[PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME]
            # sample_collection = projectName_db["sample"]
            # groupSpecification_collection = db['groupSpecification']
            project_exist = project_collection.find_one({"name": name})
            if not project_exist:
                return failResponse(data={"msg": "项目不存在"})
            else:
                if project_exist["user_id"] != str(user.id):
                    return failResponse(data={"msg": "这不是你创建的项目"})
            # 删除项目
            project_collection.delete_one({"name": name})
            sample_summary.delete_many({"project_name": project_exist["name"]})
            client.drop_database(name)
            logger.info(f"{user.username}删除项目{name}")
            # project_id = project_exist["id"]
            # samples = list(sample_collection.find({"project_id": project_id}))
            # if len(samples) > 0:
            #     for sample in samples:
            #         s_name = sample["sample"]
            #         for chain in self.seven_chain_list:
            #             sample_PROJECT_COLLECTION_NAME = db[s_name + "__" + chain + "_" + name]
            #             sample_PROJECT_COLLECTION_NAME.drop()
            # sample_collection.delete_many({"project_id": project_id})
            # groupSpecification_collection.delete_one({"name": name})
            # project_detail_collection = db[name + "_detail"]
            # project_detail_collection.drop()
            # projectName_boxplot_pvalue = db[name + "_boxplot_pvalue"]
            # projectName_boxplot_pvalue.drop()
            # gene_usage = db[name + "_gene_usage"]
            # gene_usage.drop()
            # umap = db[name + "_umap"]
            # umap.drop()
            # alignment = db[name + "_alignment"]
            # alignment.drop()
            # specify_ration = db[name + "_specify_ratio"]
            # specify_ration.drop()
            # topclone = db["topClone"]
            # topclone.delete_many({"projectName": name})
            # CDR3_length = db["CDR3_length"]
            # CDR3_length.delete_many({"projectName": name})
            # Dominant_Clone = db["Dominant_Clone_Matrix"]
            # Dominant_Clone.delete_many({"projectName": name})
            return sucessResponse()
        except Exception as e:
            print(e)
            return failResponse(data={"msg": f"删除失败{e}"})
        finally:
            client.close()


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def download_processed_file(request):
    projectName = request.GET.get("projectName", None)
    print(projectName)
    if projectName is not None and projectName != "":
        try:
            print(os.listdir(f"{PROJECT_FILE}/{projectName}"))
            target_path = f"{PROJECT_FILE}/download_file/{str(uuid.uuid4()).replace('-', '')}"
            resp = to_make_archive(target_path=target_path, archive_path=f"{PROJECT_FILE}/{projectName}")
            # target_path = f"{PROJECT_FILE}/download_file/{str(uuid.uuid4()).replace('-', '')}"
            # resp = to_make_archive(target_path=target_path, archive_path=f"{PROJECT_FILE}/download_file/{save_path}/")
            return resp
        except Exception as e:
            logger.error(f"{projectName} Error reading compressed file: {e}")

            # if name is not None and name != ""and tag is not None and tag != "":
            #     name_pattern = re.compile('.*' + re.escape(name) + '.*', re.IGNORECASE)
            #     tag_pattern = re.compile('.*' + re.escape(tag) + '.*', re.IGNORECASE)
            #     total = collection.count_documents(
            #         {'Tag': tag_pattern, 'name': name_pattern})
            #     results = collection.find({'Tag': tag_pattern, 'name': name_pattern}).skip(
            #         skip_amount).limit(size)
            # elif name is not None and name != "":
            #     name_pattern = re.compile('.*' + re.escape(name) + '.*', re.IGNORECASE)
            #     total = collection.count_documents({'name': name_pattern})
            #     results = collection.find({'name': name_pattern}).skip(skip_amount).limit(
            #         size)
            # elif tag is not None and tag != "":
            #     tag_pattern = re.compile('.*' + re.escape(tag) + '.*', re.IGNORECASE)
            #     total = collection.count_documents({'user_id': user_id, 'Tag': tag_pattern})
            #     results = collection.find({ 'Tag': tag_pattern}).skip(skip_amount).limit(
            #         size)
            # else:
            #     total = collection.count_documents({'user_id': user_id})
            #     results = collection.find({'user_id': user_id}).skip(skip_amount).limit(size)

            # project_id = project_exist["id"]
            # samples = list(sample_collection.find({"project_id": project_id}))
            # if len(samples) > 0:
            #     for sample in samples:
            #         s_name = sample["sample"]
            #         for chain in self.seven_chain_list:
            #             sample_PROJECT_COLLECTION_NAME = db[s_name + "__" + chain + "_" + name]
            #             sample_PROJECT_COLLECTION_NAME.drop()
            # sample_collection.delete_many({"project_id": project_id})
            # groupSpecification_collection.delete_one({"name": name})
            # project_detail_collection = db[name + "_detail"]
            # project_detail_collection.drop()
            # projectName_boxplot_pvalue = db[name + "_boxplot_pvalue"]
            # projectName_boxplot_pvalue.drop()
            # gene_usage = db[name + "_gene_usage"]
            # gene_usage.drop()
            # umap = db[name + "_umap"]
            # umap.drop()
            # alignment = db[name + "_alignment"]
            # alignment.drop()
            # specify_ration = db[name + "_specify_ratio"]
            # specify_ration.drop()
            # topclone = db["topClone"]
            # topclone.delete_many({"projectName": name})
            # CDR3_length = db["CDR3_length"]
            # CDR3_length.delete_many({"projectName": name})
            # Dominant_Clone = db["Dominant_Clone_Matrix"]
            # Dominant_Clone.delete_many({"projectName": name})
