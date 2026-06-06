// MongoDB initialization for Immune Repertoire Analysis
// This runs on first container startup

db = db.getSiblingDB('immune_repertoire');

// Create collections with indexes
db.createCollection('rawdata');
db.rawdata.createIndex({ project_id: 1, asset_type: 1 });
db.rawdata.createIndex({ storage_path: 1 }, { unique: true, sparse: true });

db.createCollection('results');
db.results.createIndex({ project_id: 1, analysis_type: 1 });
db.results.createIndex({ job_id: 1 }, { unique: true });

db.createCollection('analysis_cache');
db.analysis_cache.createIndex({ project_id: 1 });
db.analysis_cache.createIndex({ source_job_id: 1 });
db.analysis_cache.createIndex({ source_result_signature: 1 });
db.analysis_cache.createIndex(
  { project_id: 1, source_job_id: 1, usage_scope: 1, group_field: 1, storage_path: 1 },
  { unique: true }
);
