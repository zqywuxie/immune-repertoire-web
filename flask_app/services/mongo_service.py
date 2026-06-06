"""
MongoDB service layer for rawdata, results, and analysis cache management.
Uses pymongo directly for flexibility with unstructured data.
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
    from pymongo.database import Database
except ModuleNotFoundError:  # pragma: no cover - depends on optional runtime extra
    MongoClient = None  # type: ignore
    Collection = Any  # type: ignore
    Database = Any  # type: ignore

from flask_app.database_config import MONGO_URI, MONGO_DB_NAME

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    """Return a singleton MongoClient instance."""
    global _client
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db() -> Database:
    """Return the application database."""
    return get_mongo_client()[MONGO_DB_NAME]


def rawdata_col() -> Collection:
    """Collection for project raw data assets (pep, datapoint, raw_archive, sample_summary)."""
    return get_db()['rawdata']


def results_col() -> Collection:
    """Collection for analysis result metadata."""
    return get_db()['results']


def cache_col() -> Collection:
    """Collection for analysis cache data (e.g. cached usage from pep analysis)."""
    return get_db()['analysis_cache']


# ── rawdata helpers ──────────────────────────────────────────────

def save_rawdata_asset(
    project_id: str,
    asset_type: str,
    original_name: str,
    storage_path: str,
    size: int = 0,
    mime_type: str = '',
    columns: Optional[List[str]] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Insert or update a rawdata document. Returns the document _id as string."""
    doc = {
        'project_id': project_id,
        'asset_type': asset_type,
        'original_name': original_name,
        'storage_path': storage_path,
        'size': size,
        'mime_type': mime_type,
        'columns': columns or [],
        'metadata_json': metadata_json or {},
        'updated_at': datetime.utcnow(),
    }
    existing = rawdata_col().find_one({
        'project_id': project_id,
        'storage_path': storage_path,
    })
    if existing:
        doc['uploaded_at'] = existing.get('uploaded_at', datetime.utcnow())
        rawdata_col().update_one({'_id': existing['_id']}, {'$set': doc})
        return str(existing['_id'])
    else:
        doc['uploaded_at'] = datetime.utcnow()
        result = rawdata_col().insert_one(doc)
        return str(result.inserted_id)


def get_project_rawdata(project_id: str, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve rawdata documents for a project, optionally filtered by asset_type."""
    query: Dict[str, Any] = {'project_id': project_id}
    if asset_type:
        query['asset_type'] = asset_type
    return list(rawdata_col().find(query).sort('uploaded_at', -1))


def delete_project_rawdata(project_id: str) -> int:
    """Delete all rawdata for a project. Returns count of deleted documents."""
    result = rawdata_col().delete_many({'project_id': project_id})
    return result.deleted_count


# ── results helpers ──────────────────────────────────────────────

def _json_default(value: Any) -> str:
    if hasattr(value, 'isoformat') and callable(getattr(value, 'isoformat')):
        return value.isoformat()
    return str(value)


def _stable_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=_json_default)


def build_analysis_signature(
    *,
    project_id: str,
    analysis_type: str,
    input_assets: Optional[List[Dict[str, Any]]] = None,
    config_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a stable signature for equivalent analysis inputs and parameters."""
    payload = {
        'project_id': str(project_id or ''),
        'analysis_type': str(analysis_type or ''),
        'input_assets': input_assets or [],
        'config_json': config_json or {},
    }
    return hashlib.sha256(_stable_json(payload).encode('utf-8')).hexdigest()


def ensure_result_indexes() -> None:
    """Ensure indexes used by result lookup and de-duplication exist."""
    col = results_col()
    col.create_index([('project_id', 1), ('analysis_type', 1)])
    col.create_index([('job_id', 1)], unique=True)
    col.create_index(
        [('project_id', 1), ('analysis_type', 1), ('analysis_signature', 1)],
        unique=True,
        sparse=True,
    )


def find_result_by_signature(
    project_id: str,
    analysis_type: str,
    analysis_signature: str,
) -> Optional[Dict[str, Any]]:
    """Find a completed result for the same project/module/signature."""
    if not project_id or not analysis_type or not analysis_signature:
        return None
    ensure_result_indexes()
    return results_col().find_one({
        'project_id': project_id,
        'analysis_type': analysis_type,
        'analysis_signature': analysis_signature,
        'status': 'completed',
    })

def save_result(
    project_id: str,
    analysis_type: str,
    job_id: str,
    files: Optional[List[Dict[str, str]]] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
    analysis_signature: str = '',
    input_assets: Optional[List[Dict[str, Any]]] = None,
    config_json: Optional[Dict[str, Any]] = None,
    viewer_url: str = '',
    zip_url: str = '',
    output_base: str = '',
    status: str = 'completed',
) -> str:
    """Insert or update an analysis result document. Returns the document _id as string."""
    ensure_result_indexes()
    doc = {
        'project_id': project_id,
        'analysis_type': analysis_type,
        'job_id': job_id,
        'files': files or [],
        'metadata_json': metadata_json or {},
        'analysis_signature': analysis_signature,
        'input_assets': input_assets or [],
        'config_json': config_json or {},
        'viewer_url': viewer_url,
        'zip_url': zip_url,
        'output_base': output_base,
        'status': status,
        'updated_at': datetime.utcnow(),
    }
    query: Dict[str, Any] = {'job_id': job_id}
    if analysis_signature:
        query = {
            'project_id': project_id,
            'analysis_type': analysis_type,
            'analysis_signature': analysis_signature,
        }
    existing = results_col().find_one(query)
    if existing:
        doc['created_at'] = existing.get('created_at', datetime.utcnow())
        results_col().update_one({'_id': existing['_id']}, {'$set': doc})
        return str(existing['_id'])
    else:
        doc['created_at'] = datetime.utcnow()
        result = results_col().insert_one(doc)
        return str(result.inserted_id)


def get_project_results(project_id: str, analysis_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve result documents for a project, optionally filtered by analysis_type."""
    ensure_result_indexes()
    query: Dict[str, Any] = {'project_id': project_id}
    if analysis_type:
        query['analysis_type'] = analysis_type
    return list(results_col().find(query).sort('created_at', -1))


# ── cache helpers ────────────────────────────────────────────────

def ensure_cache_indexes() -> None:
    """Ensure cached usage indexes allow multiple scopes per source job."""
    col = cache_col()
    indexes = col.index_information()
    source_idx = indexes.get('source_job_id_1') or {}
    if source_idx.get('unique'):
        col.drop_index('source_job_id_1')
    col.create_index([('project_id', 1)])
    col.create_index([('source_job_id', 1)])
    col.create_index([('source_result_signature', 1)])
    col.create_index([
        ('project_id', 1),
        ('source_job_id', 1),
        ('usage_scope', 1),
        ('group_field', 1),
        ('storage_path', 1),
    ], unique=True)

def save_cached_usage(
    project_id: str,
    source_job_id: str,
    chains: Optional[List[str]] = None,
    group_fields: Optional[List[str]] = None,
    usage_types: Optional[Dict[str, Any]] = None,
    pep_data_dir: str = '',
    profile_path: str = '',
    storage_path: str = '',
    original_name: str = '',
    metadata_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Cache pep analysis usage data for later reuse."""
    ensure_cache_indexes()
    metadata = metadata_json or {}
    usage_scope = str(metadata.get('usage_scope') or '').strip()
    group_field = str(metadata.get('group_field') or '').strip()
    source_result_signature = str(metadata.get('source_result_signature') or '').strip()
    source_result_id = str(metadata.get('source_result_id') or '').strip()
    doc = {
        'project_id': project_id,
        'asset_type': 'cached_usage',
        'original_name': original_name or f"cached_usage_{source_job_id}",
        'storage_path': storage_path or str(metadata.get('storage_path') or ''),
        'source_job_id': source_job_id,
        'source_result_signature': source_result_signature,
        'source_result_id': source_result_id,
        'chains': chains or [],
        'group_fields': group_fields or [],
        'usage_types': usage_types or {},
        'pep_data_dir': pep_data_dir,
        'profile_path': profile_path,
        'usage_scope': usage_scope,
        'group_field': group_field,
        'metadata_json': metadata,
        'cached_at': datetime.utcnow(),
    }
    query = {
        'project_id': project_id,
        'source_job_id': source_job_id,
        'usage_scope': usage_scope,
        'group_field': group_field,
        'storage_path': doc['storage_path'],
    }
    existing = cache_col().find_one(query)
    if existing:
        cache_col().update_one({'_id': existing['_id']}, {'$set': doc})
        return str(existing['_id'])
    else:
        result = cache_col().insert_one(doc)
        return str(result.inserted_id)


def get_cached_usage(project_id: str) -> List[Dict[str, Any]]:
    """Retrieve cached usage data for a project."""
    ensure_cache_indexes()
    return list(cache_col().find({'project_id': project_id}).sort('cached_at', -1))


# ── utility ──────────────────────────────────────────────────────

def ping() -> bool:
    """Test MongoDB connectivity."""
    try:
        get_mongo_client().admin.command('ping')
        return True
    except Exception:
        return False
