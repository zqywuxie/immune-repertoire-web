"""Separate scoped registration sums from shared filesystem capacity; never walk data trees."""
from pathlib import Path
import shutil
from flask import current_app
from sqlalchemy import func
from flask_app.models.database import File,Project,ProjectAsset,db
from flask_app.services.user_scope import scope_query,is_admin


def storage_statistics():
    project_ids=scope_query(Project.query,Project).with_entities(Project.id).subquery()
    files=scope_query(File.query,File)
    assets=ProjectAsset.query.filter(ProjectAsset.project_id.in_(db.select(project_ids.c.id)))
    file_count,file_bytes=files.with_entities(func.count(File.id),func.coalesce(func.sum(File.size),0)).one()
    rows=assets.with_entities(ProjectAsset.asset_type,ProjectAsset.metadata_json['superseded'].as_boolean(),
        func.count(ProjectAsset.id),func.coalesce(func.sum(ProjectAsset.size),0)).group_by(
            ProjectAsset.asset_type,ProjectAsset.metadata_json['superseded'].as_boolean()).all()
    from flask_app.services.project_asset_service import ProjectAssetService
    categories={key:{'count':0,'bytes':0} for key in ('current_inputs','historical_inputs','results','other')}
    for kind,retired,count,size in rows:
        key=('historical_inputs' if retired else 'current_inputs') if kind in ProjectAssetService.INPUT_TYPES else 'results' if kind=='processed_result' else 'other'
        categories[key]['count']+=int(count);categories[key]['bytes']+=int(size)
    capacity=[]
    can_view_capacity=is_admin() or not current_app.config.get('REQUIRE_LOGIN',True)
    if can_view_capacity:
        seen={}
        for label,key in [('应用数据','USER_DATA_ROOT'),('项目输入','PROJECT_DATA_ROOT'),('分析结果','RESULTS_DIR')]:
            location=current_app.config.get(key)
            if not location:
                capacity.append({'labels':[label],'available':False});continue
            try:
                path=Path(location)
                device=path.stat().st_dev
                if device in seen:
                    seen[device]['labels'].append(label);continue
                usage=shutil.disk_usage(path)
                item={'labels':[label],'available':True,'total_bytes':usage.total,'used_bytes':usage.used,'free_bytes':usage.free}
                seen[device]=item;capacity.append(item)
            except OSError:
                capacity.append({'labels':[label],'available':False})
    return {'success':True,'files':int(file_count),'file_bytes':int(file_bytes),
        'assets':sum(row['count'] for row in categories.values()),'asset_bytes':sum(row['bytes'] for row in categories.values()),
        'registered_categories':categories,'filesystem_capacity':capacity,'capacity_visible':can_view_capacity,
        'cache_bytes':None}
