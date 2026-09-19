"""Read legacy MySQL, map registered Windows paths and import into an empty DB.

Source must be an isolated restored database. Application API must be stopped
before --apply. Source mounts are read-only; existing target rows are never merged.
"""
import argparse
import filecmp
import json
import re
import shutil
import sys
sys.path.insert(0, '/app')
from pathlib import Path
from datetime import datetime, timezone
from dotenv import dotenv_values
from sqlalchemy import create_engine, MetaData, select, func
from sqlalchemy.engine import URL

parser=argparse.ArgumentParser()
parser.add_argument('--apply',action='store_true')
parser.add_argument('--files-staged',action='store_true')
args=parser.parse_args()
legacy=dotenv_values('/source.env')
source=create_engine(URL.create('mysql+pymysql',username=legacy.get('MYSQL_USER','ir_user'),password=legacy.get('MYSQL_PASSWORD','ir_pass_2024'),host='immune-legacy-mysql-verify',database=legacy.get('MYSQL_DATABASE','immune_repertoire')))
from flask_app.database_config import SQLALCHEMY_DATABASE_URI
target=create_engine(SQLALCHEMY_DATABASE_URI)
source_meta,target_meta=MetaData(),MetaData()
source_meta.reflect(source);target_meta.reflect(target)
runtime=Path('/app/flask_app/data')
report={'created_at':datetime.now(timezone.utc).isoformat(),'tables':{},'mapped_paths':{},'unmapped_paths':[],'missing_assets':[],'copied_bytes':0,'copied_files':0}
extra_sources={}

def mapped(value):
    if not isinstance(value,str):return value
    normal=value.replace('\\','/')
    match=re.match(r'^[A-Za-z]:/.*?/immune-repertoire-web/(.+)$',normal,re.I)
    destination=None;origin=None
    if normal.startswith('flask_app/data/'):
        tail=normal[len('flask_app/data/'):]
        destination=runtime/tail;origin=Path('/legacy-data')/tail
    if match:
        relative=match.group(1)
        if relative.lower().startswith('flask_app/data/'):
            tail=relative[len('flask_app/data/'):]
            destination=runtime/tail;origin=Path('/legacy-data')/tail
            if tail.startswith('results/'):
                origin=Path('/legacy-results')/tail[len('results/'):]
        elif relative.lower().startswith('test_data/'):
            tail=relative[len('test_data/'):]
            destination=runtime/'imported/test_data'/tail;origin=Path('/legacy-test-data')/tail
            extra_sources[str(destination)]=origin
    external='C:/Users/Yun/Nutstore/1/实验/Research_Projects/USC_Student_Project_2024/Bioinfo_2025/Alternative_Reagent_Validation_Study/20251029_Beads_test/HUT_LS/artificial_peps'
    if normal==external or normal.startswith(external+'/'):
        tail=normal[len(external):].lstrip('/')
        destination=runtime/'imported/artificial_peps'/tail;origin=Path('/legacy-artificial')/tail
        extra_sources[str(destination)]=origin
    if destination is not None:
        if '..' in destination.parts:raise ValueError('Unsafe relative path')
        report['mapped_paths'][value]={'destination':str(destination),'exists':origin.exists()}
        return str(destination)
    if re.match(r'^[A-Za-z]:[/\\]',value) and value not in report['unmapped_paths']:
        report['unmapped_paths'].append(value)
    return value

def transform(value):
    if isinstance(value,dict):return {k:transform(v) for k,v in value.items()}
    if isinstance(value,list):return [transform(v) for v in value]
    if isinstance(value,str) and value.lstrip().startswith(('{','[')):
        try:return json.dumps(transform(json.loads(value)),ensure_ascii=False)
        except (ValueError,TypeError):pass
    return mapped(value)

records={}
with source.connect() as connection:
    for table in source_meta.sorted_tables:
        rows=[dict(row) for row in connection.execute(select(table)).mappings()]
        if rows and table.name not in target_meta.tables:raise ValueError('Unknown source table '+table.name)
        records[table.name]=[transform(row) for row in rows]
        report['tables'][table.name]=len(rows)
        if table.name in {'files','project_assets'}:
            for row in rows:
                path=row.get('storage_path','');entry=report['mapped_paths'].get(path)
                if not entry or not entry['exists']:report['missing_assets'].append({'table':table.name,'id':row['id'],'path':path})

def copy_item(origin,destination):
    if origin.is_symlink():raise ValueError('Unexpected symlink: '+str(origin))
    if origin.is_dir():
        destination.mkdir(parents=True,exist_ok=True)
        for child in origin.iterdir():copy_item(child,destination/child.name)
    elif origin.is_file():
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if not filecmp.cmp(origin,destination,shallow=False):raise ValueError('Conflicting destination: '+str(destination))
        else:
            shutil.copy2(origin,destination)
            assert origin.stat().st_size==destination.stat().st_size
            report['copied_files']+=1;report['copied_bytes']+=origin.stat().st_size

if args.apply:
    if report['missing_assets']:raise ValueError('Resolve missing registered assets before importing')
    with target.connect() as connection:
        for name,rows in records.items():
            if rows and connection.scalar(select(func.count()).select_from(target_meta.tables[name])):
                raise ValueError('Target table is not empty: '+name)
    if args.files_staged:
        report['staged_archives']=json.loads(Path('/backup/files-staged.json').read_text())
        for rows in [records.get('files',[]),records.get('project_assets',[])]:
            for row in rows:
                if not Path(row['storage_path']).exists():raise ValueError('Missing staged asset '+row['storage_path'])
    else:
        for folder in ['uploads','projects','results','reference','reference_db','users','custom_schemes','pdf_extractions']:
            origin=Path('/legacy-data')/folder
            if folder=='results':origin=Path('/legacy-results')
            if origin.exists():copy_item(origin,runtime/folder)
        for destination,origin in sorted(extra_sources.items(),key=lambda item:len(item[0])):
            if origin.exists():copy_item(origin,Path(destination))
    with target.begin() as connection:
        for table in target_meta.sorted_tables:
            rows=records.get(table.name,[])
            for row in rows:
                unknown=set(row)-set(table.columns.keys())
                if unknown:raise ValueError('Unmapped columns: '+str(unknown))
                if table.name=='analysis_jobs' and row.get('status') in {'queued','running'}:
                    row.update(status='interrupted',detail='旧环境任务已中断，请检查参数后重新运行。',completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
            if rows:connection.execute(table.insert(),rows)
        for name,rows in records.items():
            if rows:assert connection.scalar(select(func.count()).select_from(target_meta.tables[name]))==len(rows)
    report['imported']=True

destination=Path('/backup')/('migration-applied.json' if args.apply else 'migration-plan.json')
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='mapped_paths'},ensure_ascii=False,default=str))
print('Mapped paths:',len(report['mapped_paths']))
