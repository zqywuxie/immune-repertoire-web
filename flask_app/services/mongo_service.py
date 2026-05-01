"""
MongoDB service layer for rawdata, results, and analysis cache management.
Uses pymongo directly for flexibility with unstructured data.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from flask_app.database_config import MONGO_URI, MONGO_DB_NAME

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    """Return a singleton MongoClient instance."""
    global _client
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

def save_result(
    project_id: str,
    analysis_type: str,
    job_id: str,
    files: Optional[List[Dict[str, str]]] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Insert or update an analysis result document. Returns the document _id as string."""
    doc = {
        'project_id': project_id,
        'analysis_type': analysis_type,
        'job_id': job_id,
        'files': files or [],
        'metadata_json': metadata_json or {},
        'updated_at': datetime.utcnow(),
    }
    existing = results_col().find_one({'job_id': job_id})
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
    query: Dict[str, Any] = {'project_id': project_id}
    if analysis_type:
        query['analysis_type'] = analysis_type
    return list(results_col().find(query).sort('created_at', -1))


# ── cache helpers ────────────────────────────────────────────────

def save_cached_usage(
    project_id: str,
    source_job_id: str,
    chains: Optional[List[str]] = None,
    group_fields: Optional[List[str]] = None,
    usage_types: Optional[Dict[str, Any]] = None,
    pep_data_dir: str = '',
    profile_path: str = '',
    metadata_json: Optional[Dict[str, Any]] = None,
) -> str:
    """Cache pep analysis usage data for later reuse."""
    doc = {
        'project_id': project_id,
        'source_job_id': source_job_id,
        'chains': chains or [],
        'group_fields': group_fields or [],
        'usage_types': usage_types or {},
        'pep_data_dir': pep_data_dir,
        'profile_path': profile_path,
        'metadata_json': metadata_json or {},
        'cached_at': datetime.utcnow(),
    }
    existing = cache_col().find_one({'source_job_id': source_job_id})
    if existing:
        cache_col().update_one({'_id': existing['_id']}, {'$set': doc})
        return str(existing['_id'])
    else:
        result = cache_col().insert_one(doc)
        return str(result.inserted_id)


def get_cached_usage(project_id: str) -> List[Dict[str, Any]]:
    """Retrieve cached usage data for a project."""
    return list(cache_col().find({'project_id': project_id}).sort('cached_at', -1))


# ── utility ──────────────────────────────────────────────────────

def ping() -> bool:
    """Test MongoDB connectivity."""
    try:
        get_mongo_client().admin.command('ping')
        return True
    except Exception:
        return False
