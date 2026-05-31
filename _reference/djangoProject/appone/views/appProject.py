import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, authentication_classes, permission_classes
import pandas as pd
from pymongo import MongoClient
import uuid
import datetime
from appone.result.myResponse import *
from appone.constant import DBURL,CHAIN_TYPES
from djangoProject.settings import MY_GLOBAL_List
import  parmap
from datetime import datetime
from  appone.constant import PROJECT_DB_NAME,PROJECT_COLLECTION_NAME,PROJECT_DATAPOINT_COLLECTION_NAME,PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME
import zipfile
import tarfile
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from djangoProject.tools.logger import log
from djangoProject.settings import TAR_DIR
logger = log.GetLogger().get_logger()

# 添加项目
class addProject(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        res = check_feild_to_request(request,"POST","cooperation_level","projectName","institution")
        if res:
            return res
        projectName = request.data.get('projectName')
        institution = request.data.get('institution')
        cooperation_level = request.data.get('cooperation_level')
        try:
            client = MongoClient(DBURL, maxidletimems=120000)
            db = client[PROJECT_DB_NAME]
            project_collection = db[PROJECT_COLLECTION_NAME]
            project_exist = project_collection.find_one({"name": projectName})
            if project_exist:
                return failResponse(msg="项目已存在")
            data = {
                'name': projectName,
                'id': str(uuid.uuid4()),
                'user_id': str(user.id),
                "cooperation_level":cooperation_level,
                "institution":institution,
                "create_time":datetime.now().strftime("%Y-%m-%d %H:%M"),
                "is_datapoint": "False",
                "is_pep": "False",
                "is_GroupSpecification":"False",
                "is_processed": "False",
            }
            project_collection.insert_one(data)
            logger.info(f"{request.user}:添加{projectName}")
            return sucessResponse(msg='添加成功')
        except Exception as e:
            print(e)
            logger.info(f"{request.user}:{projectName}添加失败：{e}")
            return failResponse(msg="上传失败")
        finally:
            # 关闭连接
            client.close()


class addDatapoint(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        projectName = request.data.get('projectName')
        file = request.FILES.get('file')

        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[PROJECT_DB_NAME]
        project_collection = db[PROJECT_COLLECTION_NAME]
        pro_exist = project_collection.find_one({"name": projectName})
        if not pro_exist:
            return failResponse(msg="项目不存在")
        resp = is_my_project(user, projectName)
        if resp:
            return resp
        if  project_collection.find_one({"name": projectName})["is_datapoint"] == "True":
            client.close()
            return failResponse(msg="datapoint已上传过了")
        # print(file)
        df = pd.read_csv(file)
        resp = insert_datapoint(projectName,df)
        client.close()
        if resp:
            return resp
        logger.info(f"{request.user}:{projectName}上传datapoint成功")
        return sucessResponse(msg="上传成功")

class addGroupSpecification(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        res = check_feild_to_request(request,"POST","projectName","groupSpecification")
        if res:
            return res
        projectName = request.data.get('projectName')
        groupSpecification = request.data.get('groupSpecification')
        # print("groupSpecification:",type(groupSpecification),groupSpecification)
        # return sucessResponse(msg="上传成功")
        try:
            client = MongoClient(DBURL, maxidletimems=120000)
            project_db = client[PROJECT_DB_NAME]
            projectName_db = client[projectName]
            project_collection = project_db[PROJECT_COLLECTION_NAME]
            groupSpecification_collection = projectName_db['groupSpecification']
            pro_exist = project_collection.find_one({"name": projectName})
            if not pro_exist:
                return failResponse(msg="项目不存在")
            resp = is_my_project(user, projectName)
            if resp:
                client.close()
                return resp
            if project_collection.find_one({"name": projectName})["is_GroupSpecification"] == "True":
                client.close()
                return failResponse(msg="roupSpecification已上传过了")
            # print("groupSpecification",groupSpecification,type(groupSpecification))
            groupSpecification_collection.update_one({"name": projectName}, {"$set": {"groupSpecification": groupSpecification}},upsert=True)
            # project_collection.update_one({"name": projectName}, {"$set": {"is_GroupSpecification": "True"}})
            project_collection.update_one({"name": projectName}, {"$set": {"is_GroupSpecification": "True"}})
            if is_add_MY_GLOBAL_List(projectName, project_collection):
                # MY_GLOBAL_List.append(projectName)
                # logger.info("MY_GLOBAL_List有新增",MY_GLOBAL_List)
                from appone.constant import PROJECT_LIST
                import  json
                with open(PROJECT_LIST, "r+") as f:
                    dict_b = json.load(f)
                dict_b["project_list"].append(projectName)
                with open(PROJECT_LIST, "w") as outfile:
                    json.dump(dict_b, outfile)
                logger.info(f"MY_GLOBAL_List有新增 {projectName}")
            logger.info(f"{request.user}:{projectName}上传groupSpecification成功")
            return sucessResponse(msg="上传groupSpecification成功")
        except Exception as e:
            # print(e)
            logger.error(f"{request.user}:{projectName}上传groupSpecification失败{e}")
            return failResponse(msg=f"上传groupSpecification失败{e}")
        finally:
            client.close()
class addPep(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        projectName = request.data.get('projectName')
        files = request.FILES.getlist('file')
        if len(files) ==1 and ("gz" in files[0].name or "zip"in files[0].name):
            try:
                from  appone.constant import PROJECT_FILE
                file = files[0]
                if not os.path.exists(f'{TAR_DIR}/'):
                    os.makedirs(f'{TAR_DIR}/')
                path = default_storage.save(f'{TAR_DIR}/{file.name}', ContentFile(file.read()))
                tmp_file_path = default_storage.path(path)
                logger.info(tmp_file_path)
                save_dir = str(uuid.uuid4())
                if tmp_file_path.endswith('.gz'):
                    with tarfile.open(tmp_file_path, 'r:gz') as tar_ref:
                        tar_ref.extractall(path=f'{TAR_DIR}/{save_dir}')
                else:
                    with zipfile.ZipFile(tmp_file_path, 'r') as zip_ref:
                        zip_ref.extractall(f'{TAR_DIR}/{save_dir}')
                file_list = []
                for dir,dirs,files in os.walk(f'{TAR_DIR}/{save_dir}'):
                    for file in files:
                        if file.endswith('.csv'):
                            file_list.append(os.path.join(dir, file))
                # print("file_list:",file_list)
                return  addPee_by_csvfiles(files = file_list,projectName=projectName,user=user)
                # return addPee_by_csvfiles(files = file_list)
            except Exception as e:
                return Response({"error": str(e)}, status=500)
        # print(f"pep{files}")
        else:
            return addPee_by_csvfiles(files = files,projectName = projectName,user=user)

# 上传样品总表
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def insert_sample_Summary_Table(request):
    check_feild_to_request(request,"POST","projectName")
    projecName = request.data.get('projectName')
    sample_describe = request.FILES.get('file')
    if not sample_describe:
        return failResponse(msg="请上传文件")
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        project_db = client[PROJECT_DB_NAME]
        project_collection = project_db[PROJECT_COLLECTION_NAME]
        pro_exist = project_collection.find_one({"name": projecName})
        if not pro_exist:
            return failResponse(msg="项目不存在")
        sample_describe_collection = project_db[PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME]
        sample_describe_collection.delete_many({"project_name": projecName})
        institution = pro_exist["institution"]
        project_name = pro_exist["name"]
        # csv or xlsx
        if sample_describe.name.endswith('.xlsx'):
            df = pd.read_excel(sample_describe)
        else:
            df = pd.read_csv(sample_describe)
        df = pd.read_csv(sample_describe)
        df["project_name"] = project_name
        row_count =  df.shape[0]
        # df['id'] = [str(uuid.uuid4()) for _ in range(row_count)]
        df['id'] = [f"{projecName}_sample{_}" for _ in range(row_count)]
        df["create_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        df["institution"] = institution
        sample_describe_collection.insert_many(df.to_dict(orient='records'))
        return sucessResponse(msg="上传成功")
    except Exception as e:
        print(e)
        return failResponse(msg=f"出现错误：{e}")
    finally:
        client.close()

def insert_datapoint(projectName,file):
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        project_db = client[PROJECT_DB_NAME]
        projectName_db = client[projectName]
        project_collection = project_db[PROJECT_COLLECTION_NAME]
        sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
        project_exist = project_collection.find_one({"name": projectName})
        # 先删除已有的，在增加
        sample_collection.drop()
        df = file
        row_count = df.shape[0]
        # df['id'] = [str(uuid.uuid4()) for _ in range(row_count)]
        df['project_id'] = project_exist['id']
        # print(db)
        data_dict = df.to_dict(orient='records')
        sample_collection.insert_many(data_dict)
        project_collection.update_one({"name": projectName}, {"$set": {"is_datapoint": "True"}})
    except Exception as e:
        print(e)
        return  failResponse(msg=f"上传失败{e}")
    finally:
        # 关闭连接
        client.close()


def insert_one_pep(data):
    projectName = data[0]
    df  = data[1]
    # file_name = file.name
    # print("上传的文件名为：", file_name)
    orginal_file_name = data[2]
    sample_name = data[3]
    # print("sample_name", sample_name)
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        # project_collection = db['project']
        sample_collection = db[PROJECT_DATAPOINT_COLLECTION_NAME]
        sampleName_TRA = db[orginal_file_name + "_" + projectName]
        projectName_detail = db[projectName + "_detail"]

        df = df #pd.read_csv(file,low_memory=False)
        # sample_id = sample_collection.find_one({"sample": sample_name})['id']
        # df['sample_id'] = sample_id
        row_count = df.shape[0]
        df['joinedSeq_id'] = [str(uuid.uuid4()) for _ in range(row_count)]
        # df_sampleName_TRA = df[["CDR3(pep)","joinedSeq_id", "sample_id", "V","J","copy"]].to_dict(orient='records')
        sampleName_TRA.drop()
        df_sampleName_TRA = df.to_dict(orient='records')
        sampleName_TRA.insert_many(df_sampleName_TRA)
        if {"joinedSeq_id", "joinedSeq", "V", "D", "J", "C"}.issubset(df.columns):
            df_sampleName_detail = df[["joinedSeq_id", "joinedSeq", "V", "D", "J", "C"]].to_dict(orient='records')
            df_sampleName_detail = df.to_dict(orient='records')
            projectName_detail.insert_many(df_sampleName_detail)
        return 1
    except Exception as e:
        logger.info(f"{projectName}上传{orginal_file_name}失败{e},请全部重新上传")
        print(e)
        return  f"上传{orginal_file_name}失败{e},请全部重新上传"
    finally:
        # 关闭连接
        client.close()


def is_my_project(user, projectName):
    try:
        client = MongoClient(DBURL, maxidletimems=120000)
        db = client[PROJECT_DB_NAME]
        project_collection = db[PROJECT_COLLECTION_NAME]
        project_exist = project_collection.find_one({"name": projectName})
        if not project_exist:
            return failResponse(msg="项目不存在")
        else:
            if project_exist["user_id"] != str(user.id):
                return  failResponse(msg="这不是你创建的项目")
    except Exception as e:
        print(e)
    finally:
        client.close()


# 查找，携带名字列表，拿到所有collection名字，in
def is_add_MY_GLOBAL_List(projectName,project_collection):
    pro = project_collection.find_one({"name": projectName})
    if pro["is_datapoint"] == "True" and pro["is_pep"] == "True" and pro["is_GroupSpecification"] == "True":
        return True
    else:
        return False


def check_feild_to_request(request,resquest_method = "POST" ,*args):
    if resquest_method == "POST":
        for arg in args:
            if arg not in request.data:
                return failResponse(msg=f"{arg}为必填项")
    elif resquest_method == "GET":
        for arg in args:
            if arg not in request.GET:
                return failResponse(msg=f"{arg}为必填项")



def addPee_by_csvfiles(files,projectName,user):
    client = MongoClient(DBURL, maxidletimems=120000)
    project_db = client[PROJECT_DB_NAME]
    projectName_db = client[projectName]
    project_collection = project_db[PROJECT_COLLECTION_NAME]
    groupSpecification_collection = projectName_db['groupSpecification']
    pro_detail = projectName_db[f"{projectName}_detail"]
    sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
    pro_exist = project_collection.find_one({"name": projectName})
    if not pro_exist:
        return failResponse(msg="项目不存在")
    resp = is_my_project(user, projectName)
    if resp:
        client.close()
        return resp
    pro_id = project_collection.find({'name': projectName})[0]["id"]
    document = sample_collection.find({'project_id': pro_id}, {"_id": 0, "sample": 1})
    documents_list = list(document)
    datapoint = pd.DataFrame(documents_list)

    if project_collection.find_one({"name": projectName})["is_datapoint"] == "False":
        client.close()
        return failResponse(msg="请先上传datapoint")

    if project_collection.find_one({"name": projectName})["is_pep"] == "True":
        client.close()
        return failResponse(msg="pep文件已上传过了")
    if not files:
        client.close()
        logger.info(f"{request.user}:{projectName}上传pep，请上传文件")
        return failResponse(msg="请上传文件")

    # for f in files:
    #     file_name = f.name
    #     orginal_file_name = file_name[:-4][:-5]
    #     is_in_column = orginal_file_name in datapoint["sample"].values
    #     if not is_in_column:
    #         client.close()
    #         logger.info(
    #             f"{request.user}:文件名{f}与datapoint不匹配,请重新上传")
    #         logger.info(f"{request.user}:文件名{f}与datapoint不匹配,请重新上传")
    #         project_collection.update_one({"name": projectName}, {"$set": {"is_datapoint": "False"}})
    #         return failResponse(msg=f"文件名{f}与datapoint不匹配,请重新上传")

    resp = is_my_project(user, projectName)
    if resp:
        client.close()
        return resp
    datas = []
    for file in files:
        df = pd.read_csv(file)
        if isinstance(file, str):
            file_name = os.path.basename(file)
            orginal_file_name = file_name[:-4]
            sample_name = orginal_file_name[:-5]
        else:
            file_name = file.name
            orginal_file_name = file_name[:-4]
            sample_name = orginal_file_name[:-5]
        data = [projectName, df, orginal_file_name, sample_name]
        datas.append(data)
    runtime = parmap.map_async(insert_one_pep, datas)
    runtime.wait()
    result = runtime.get()
    # result = []
    # for data in datas:
    #     result.append(insert_one_pep(data))
    for resp in result:
        # resp = insert_one_pep(projectName,f)
        if resp != 1:
            # 删除已经上传的文件，重新上传
            project_id = pro_id
            samples = list(sample_collection.find({"project_id": project_id}))
            if len(samples) > 0:
                for sample in samples:
                    s_name = sample["sample"]
                    for chain in CHAIN_TYPES:
                        sample_PROJECT_COLLECTION_NAME = db[s_name + "__" + chain + "_" + projectName]
                        sample_PROJECT_COLLECTION_NAME.drop()
            pro_detail.drop()
            sample_collection.delete_many({"project_id": project_id})
            project_collection.update_one({"name": projectName}, {"$set": {"is_GroupSpecification": "False"}})
            project_collection.update_one({"name": projectName}, {"$set": {"is_datapoint": "False"}})
            project_collection.update_one({"name": projectName}, {"$set": {"is_pep": "False"}})
            groupSpecification_collection.delete_one({"name": projectName})
            client.close()
            return failResponse(msg=resp)
    project_collection.update_one({"name": projectName}, {"$set": {"is_pep": "True"}})

    # if is_add_MY_GLOBAL_List(projectName, project_collection):
    #     MY_GLOBAL_List.append(projectName)
    #     print("MY_GLOBAL_List有新增", MY_GLOBAL_List)
    client.close()
    logger.info(f"{projectName}上传pep成功")
    return sucessResponse(msg="上传成功")

# file_name = file.name
        # print("上传的文件名为：", file_name)
        # orginal_file_name = file_name[:-4]
        # sample_name = orginal_file_name[:-5]
        # print("sample_name", sample_name)
        # try:
        #     client = MongoClient('localhost', 27017)
        #     db = client['djangoProject']
        #     project_collection = db['project']
        #     sample_collection = db['sample']
        #     sampleName_TRA = db[orginal_file_name + "_" + projectName]
        #     projectName_detail = db[projectName + "_detail"]
        #     project_exist = project_collection.find_one({"name": projectName})
        #     if not project_exist:
        #         return Response({"msg": "项目不存在"})
        #     else:
        #         if project_exist["user_id"] != str(user.id):
        #             return Response({"msg": "这不是你创建的项目"})
        #     db = pd.read_csv(file)
        #     sample_id = sample_collection.find_one({"sample": sample_name})['id']
        #     db['sample_id'] = sample_id
        #     row_count = db.shape[0]
        #     db['joinedSeq_id'] = [str(uuid.uuid4()) for _ in range(row_count)]
        #     df_sampleName_TRA = db[["joinedSeq_id","sample_id","copy"]].to_dict(orient='records')
        #     sampleName_TRA.insert_many(df_sampleName_TRA)
        #     df_sampleName_detail = db[["joinedSeq_id","joinedSeq","V","D","J","C"]].to_dict(orient='records')
        #     projectName_detail.insert_many(df_sampleName_detail)
        #     return Response({"code":200,"message": "上传成功"})
        # except Exception as e:
        #     print(e)
        #     return Response({"msg": f"上传失败{e}")
        # finally:
        #     # 关闭连接
        #     client.close()
