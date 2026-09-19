"""Import restored MongoDB documents without overwriting destination records."""
import json,re,sys
from pathlib import Path
from pymongo import MongoClient
from bson import json_util
sys.path.insert(0,'/app')
from flask_app.database_config import MONGO_URI,MONGO_DB_NAME
source=MongoClient('mongodb://immune-legacy-mongo-verify:27017')['immune_repertoire']
target=MongoClient(MONGO_URI)[MONGO_DB_NAME]
mapped=json.loads(Path('/backup/migration-applied.json').read_text())['mapped_paths']
unknown=[];count=0
def transform(value):
    global count
    if isinstance(value,dict):return {k:transform(v) for k,v in value.items()}
    if isinstance(value,list):return [transform(v) for v in value]
    if not isinstance(value,str):return value
    if value in mapped:
        count+=1
        return mapped[value]['destination']
    normal=value.replace('\\','/')
    match=re.match(r'^[A-Za-z]:/.*?/immune-repertoire-web/(flask_app/data|test_data)/(.+)$',normal,re.I)
    if match:
        suffix=match.group(2)
        if '..' in Path(suffix).parts:raise ValueError('Unsafe source path')
        count+=1
        return '/app/flask_app/data/'+('imported/test_data/' if match.group(1)=='test_data' else '')+suffix
    if re.match(r'^[A-Za-z]:[/\\]',value):unknown.append(value)
    return value
documents={name:list(source[name].find({})) for name in source.list_collection_names()}
Path('/backup/mongo-documents.json').write_text(json_util.dumps(documents))
transformed=transform(documents)
if unknown:raise ValueError('Unmapped Mongo paths: '+str(sorted(set(unknown))))
assert all(target[name].count_documents({})==0 for name in documents),'Destination is not empty'
for name,rows in transformed.items():
    if rows:target[name].insert_many(rows)
    assert target[name].count_documents({})==len(rows)
report={'collections':{name:len(rows) for name,rows in documents.items()},'mapped_paths':count}
Path('/backup/mongo-migration.json').write_text(json.dumps(report,indent=2))
print(report)
