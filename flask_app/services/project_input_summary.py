"""Read-only sample coverage from existing input validation; authorized ZIP downloads."""
from types import SimpleNamespace
from pathlib import Path
from tempfile import SpooledTemporaryFile
import zipfile
from flask import send_file
from flask_app.exceptions import ValidationError

ALIASES = {'datapoint': 'profile', 'cibersort': 'deconvolution'}
SCOPE_KEYS = ('asset_set', 'dataset', 'data_set', 'group_label', 'group')


def projected_input_assets(query):
    """Stream coverage inputs without loading unrelated asset metadata or ORM entities."""
    from flask_app.models.database import ProjectAsset
    columns = (ProjectAsset.id, ProjectAsset.asset_type, ProjectAsset.original_name,
               *(ProjectAsset.metadata_json[key] for key in SCOPE_KEYS),
               ProjectAsset.metadata_json['validation'])
    for row in query.with_entities(*columns).yield_per(100):
        identifier, kind, name, *values = row
        metadata = {key: value for key, value in zip(SCOPE_KEYS, values[:-1]) if value is not None}
        if values[-1] is not None:
            metadata['validation'] = values[-1]
        yield SimpleNamespace(id=identifier, asset_type=kind, original_name=name, metadata_json=metadata)


def normalize_sample_identifier(identifier):
    """Use the existing coverage text identity rule across catalog counts."""
    return str(identifier).strip()


def _report_sample_ids(reports):
    for report in reports or []:
        for identifier in report.get('samples') or []:
            sample = normalize_sample_identifier(identifier)
            if sample:
                yield sample


def iter_input_sample_ids(query):
    """Read identifiers only for registration membership and batch templates."""
    from flask_app.models.database import ProjectAsset
    for (reports,) in query.with_entities(ProjectAsset.metadata_json['validation']['summary']['inputs']).yield_per(100):
        yield from _report_sample_ids(reports)


def input_sample_summary(assets, search='', state=''):
    rows, unresolved = {}, []
    folded_search = search.casefold()
    versions, input_scopes = {}, {}
    for asset in assets:
        metadata = asset.metadata_json or {}
        from flask_app.services.project_asset_service import ProjectAssetService
        dataset = ProjectAssetService.dataset_name(asset)
        kind = ALIASES.get(asset.asset_type, asset.asset_type)
        versions.setdefault((dataset, kind), set()).add(asset.id)
        validation = metadata.get('validation') or {}
        reports = (validation.get('summary') or {}).get('inputs') or []
        has_samples = any(report.get('samples') for report in reports)
        scope = input_scopes.setdefault(dataset, {})
        type_scope = scope.setdefault(kind, {'asset_count': 0, 'unresolved_count': 0})
        type_scope['asset_count'] += 1
        # A partially identified or failed input cannot prove an identifier is absent.
        if validation.get('status') != 'valid' or not has_samples:
            type_scope['unresolved_count'] += 1
        # The same file description is shared across rows, while each sample retains
        # its full source list. Scope/version/unknown counts still use every input.
        source = {'asset_id': asset.id, 'name': asset.original_name,
                  'status': validation.get('status', 'unknown')}
        for sample in _report_sample_ids(reports):
            if folded_search and folded_search not in sample.casefold():
                continue
            key = (dataset, sample)
            entry = rows.get(key)
            if entry is None:
                entry = rows[key] = {'sample_id': sample, 'asset_set': dataset, 'coverage': {}, 'asset_ids': []}
            entry['coverage'].setdefault(kind, []).append(source)
            entry['asset_ids'].append(asset.id)
        if not reports or not any(report.get('samples') for report in reports):
            needs_refresh = kind == 'pep' and validation.get('status') == 'valid' and (validation.get('key') or {}).get('validator', 0) < 6
            unresolved.append({'asset_id': asset.id, 'name': asset.original_name, 'asset_set': dataset,
                               'kind': kind, 'status': 'needs_refresh' if needs_refresh else validation.get('status', 'unknown')})
    samples = []
    for key, entry in sorted(rows.items()):
        entry['needs_version_selection'] = any(len(versions.get((entry['asset_set'], kind), [])) > 1
                                               for kind in entry['coverage'] if kind != 'pep')
        if state == 'multiple' and not entry['needs_version_selection']:
            continue
        if state == 'needs_attention':
            known_problem = any(source['status'] != 'valid' for sources in entry['coverage'].values() for source in sources)
            missing_unconfirmed = any(info['unresolved_count'] for kind, info in input_scopes[entry['asset_set']].items()
                                      if kind not in entry['coverage'])
            if not known_problem and not missing_unconfirmed:
                continue
        samples.append(entry)
    return {'samples': samples, 'unresolved': unresolved, 'input_scopes': input_scopes,
            'note': '由输入文件校验结果识别；不同编号不自动视为同一样本，多版本需在分析中明确选择。'}


def download_asset_selection(assets, resolve):
    archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            for asset in assets:
                source = resolve(asset)
                prefix = f'{asset.id[:8]}_{Path(asset.original_name).name}'
                if source.is_file():
                    output.write(source, prefix)
                else:
                    files = [path for path in source.rglob('*') if path.is_file() and not path.is_symlink()
                             and path.resolve().is_relative_to(source.resolve())]
                    if not files:
                        raise ValidationError(message=f'文件夹中没有可下载文件：{asset.original_name}')
                    for path in files:
                        output.write(path, f'{prefix}/{path.relative_to(source).as_posix()}')
        archive.seek(0)
        response = send_file(archive, mimetype='application/zip', as_attachment=True, download_name='项目文件.zip')
        response.call_on_close(archive.close)
        return response
    except Exception:
        archive.close()
        raise


def add_registration_status(project_id, samples, *, complete_scope=False):
    """Project registration identities; stream a full scope once when filtering before paging."""
    from sqlalchemy import and_, or_
    from flask_app.models.database import SampleRecord
    wanted = {(row['asset_set'], row['sample_id']) for row in samples}
    if not wanted:
        return
    scopes = {}
    for dataset, identifier in wanted:
        scopes.setdefault(dataset, set()).add(identifier)
    metadata = SampleRecord.extra_metadata
    conditions = [and_(metadata['asset_set'].as_string() == dataset,
        or_(metadata['input_sample_id'].as_string().in_(identifiers),
            SampleRecord.sample_id.in_(identifiers))) for dataset, identifiers in scopes.items()]
    counts = dict.fromkeys(wanted, 0)
    # JSON extraction alone cannot distinguish missing keys from explicit null.
    # Keep the existing missing-only fallback using a bounded metadata projection.
    predicate = metadata['asset_set'].as_string().in_(scopes) if complete_scope else or_(*conditions)
    candidates = SampleRecord.query.filter(SampleRecord.project_id == project_id,
        predicate).with_entities(SampleRecord.sample_id, metadata)
    for original, attributes in candidates.yield_per(100):
        attributes = attributes or {}
        key = (attributes.get('asset_set'), attributes.get('input_sample_id', original))
        if isinstance(key[1], str) and key in counts:
            counts[key] += 1
    for row in samples:
        count = counts[(row['asset_set'], row['sample_id'])]
        row['registration'] = {'status': 'unregistered' if count == 0 else 'registered' if count == 1 else 'multiple',
                               'count': count}
