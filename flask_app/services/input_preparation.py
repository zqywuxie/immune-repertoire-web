"""Explicit table preparation; originals stay unchanged and outputs are registered assets."""
from pathlib import Path
from itertools import repeat
from uuid import uuid4
from flask_app.exceptions import ValidationError
from flask_app.models.database import ProjectAsset, db
from flask_app.services.path_access_service import PathAccessService


def normalize_sample_mappings(entries, batch_field=None):
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValidationError(message='样本编号对应必须是逐条填写的映射列表。')
    result, sources, targets = [], set(), set()
    for entry in entries:
        required = ('source_sample', 'target_sample', 'source_batch') if batch_field else ('source_sample', 'target_sample')
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key].strip() for key in required
        ):
            raise ValidationError(message='每条样本编号对应都需要填写原编号和统一编号；启用批次时还需填写原批次。')
        if not batch_field and 'source_batch' in entry:
            raise ValidationError(message='填写了原批次，请先选择样本批次字段。')
        source, target = entry['source_sample'].strip(), entry['target_sample'].strip()
        batch = entry['source_batch'].strip() if batch_field else ''
        source_key, target_key = (batch, source), (batch, target)
        if source_key in sources or target_key in targets:
            raise ValidationError(message='样本编号对应必须一对一，同一批次内的原编号和统一编号均不可重复。')
        sources.add(source_key)
        targets.add(target_key)
        result.append({'source_sample': source, 'target_sample': target, **({'source_batch': batch} if batch_field else {})})
    return result


class _SampleIdMapping:
    def __init__(self, entries, batch_field=None):
        self.batch_field = batch_field
        self.lookup = {(item.get('source_batch', ''), item['source_sample']): item['target_sample']
                       for item in normalize_sample_mappings(entries, batch_field)}
        self.seen = set()

    def rewrite(self, values, batches=None):
        if self.batch_field and batches is None:
            raise ValidationError(message='样本编号映射缺少原始批次列。')
        result = []
        for value, raw_batch in zip(values, batches if self.batch_field else repeat("")):
            sample = str(value).strip()
            batch = str(raw_batch).strip() if self.batch_field else ''
            key = (batch, sample)
            if key in self.lookup:
                self.seen.add(key)
            result.append(self.lookup.get(key, sample))
        return result

    def check_sources(self):
        missing = sorted(set(self.lookup) - self.seen)
        if missing:
            labels = [f'{batch} / {sample}' if batch else sample for batch, sample in missing[:20]]
            raise ValidationError(message='以下原编号或批次不在所选数据中，请核对编号及工作表：' + '、'.join(labels))


def analysis_input_path(asset):
    mapping = (asset.metadata_json or {}).get('input_preparation')
    if not mapping:
        return asset.storage_path
    source = PathAccessService.validate_read_path(asset.storage_path)
    stat = source.stat()
    if stat.st_size != mapping['source_size'] or stat.st_mtime_ns != mapping['source_mtime_ns']:
        raise ValidationError(message='原始文件已改变，请重新确认工作表和列映射。')
    prepared = db.session.get(ProjectAsset, mapping['prepared_asset_id'])
    if not prepared or prepared.project_id != asset.project_id or prepared.asset_type != 'prepared_input':
        raise ValidationError(message='整理后的输入已删除，请重新整理数据。')
    path = PathAccessService.validate_read_path(prepared.storage_path)
    stat = path.stat()
    if stat.st_size != mapping['prepared_size'] or stat.st_mtime_ns != mapping['prepared_mtime_ns']:
        raise ValidationError(message='整理后的输入已改变，请重新整理数据。')
    return str(path)


def prepared_source_summary(source, schema, kind, identifier, orientation, quality, batch_field=None):
    """Use checked prepared content while retaining original management sample identity."""
    from copy import deepcopy
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _CSV_ENCODINGS, _robust_read_csv
    summary = deepcopy(quality)
    samples, keys = set(), set()
    if kind == 'transcriptome' and orientation == 'genes_are_rows':
        samples.update(str(column).strip() for column in schema['columns'] if column != identifier and str(column).strip())
        keys.update(samples)
    else:
        fields = [identifier] + ([batch_field] if batch_field else [])
        def collect(frames):
            samples.clear(); keys.clear()
            for frame in frames:
                for row in frame[fields].itertuples(index=False, name=None):
                    sample = str(row[0]).strip()
                    if sample:
                        samples.add(sample)
                        keys.add((str(row[1]).strip(), sample) if batch_field else sample)
        if source.suffix.lower() in {'.xlsx', '.xlsm'}:
            collect(iter_workbook_frames(source, schema))
        elif source.suffix.lower() == '.xls':
            collect([_robust_read_csv(source, dtype=str, keep_default_na=False, sheet_name=schema['selected_sheet'], usecols=fields)])
        else:
            for encoding in dict.fromkeys([*_CSV_ENCODINGS, 'latin-1']):
                try:
                    with pd.read_csv(source, encoding=encoding, dtype=str, keep_default_na=False,
                                     usecols=fields, chunksize=5000,
                                     sep='\t' if source.suffix.lower() == '.tsv' else ',') as reader:
                        collect(reader)
                    break
                except UnicodeError:
                    continue
            else:
                raise ValidationError(message='无法读取原始样本编号，请重新确认文件编码。')
    for report in summary.get('inputs', []):
        if report.get('kind') == kind:
            report.update(samples=sorted(samples), sample_count=len(keys), columns=schema['columns'],
                          sample_column='列名（首列为基因）' if kind == 'transcriptome' and orientation == 'genes_are_rows' else identifier)
    return summary


def validate_prepared_source(asset):
    from flask_app.services.input_table_schema import inspect_table_schema
    from flask_app.services.input_quality import validate_analysis_inputs
    from flask_app.services.input_validation_cache import snapshot
    mapping = asset.metadata_json['input_preparation']
    path = analysis_input_path(asset)
    source = Path(asset.storage_path)
    before = snapshot(source)
    kind = {'datapoint':'profile', 'cibersort':'deconvolution'}.get(asset.asset_type, asset.asset_type)
    quality = validate_analysis_inputs([{'asset_type':kind,'path':path}], {'batch_field':mapping.get('batch_field')})
    schema = inspect_table_schema(source, mapping.get('sheet_name'))
    summary = prepared_source_summary(source, schema, kind, mapping['identifier_column'],
        mapping.get('orientation', 'genes_are_rows'), quality, mapping.get('batch_field'))
    if snapshot(source) != before:
        raise ValidationError(message='校验期间原始文件发生变化，请重新确认映射。')
    asset.metadata_json = {**asset.metadata_json, 'validation':
        {'status':'valid', 'prepared_asset_id':mapping['prepared_asset_id'], 'summary':summary}}
    db.session.commit()
    return summary


def prepare_table(asset, options, projects_root):
    from flask_app.services.input_table_schema import inspect_table_schema
    from flask_app.services.input_quality import SAMPLE_COLUMNS, validate_analysis_inputs
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    kind = {'datapoint':'profile','expression':'transcriptome','cibersort':'deconvolution'}.get(asset.asset_type, asset.asset_type)
    if kind not in {'profile','transcriptome','deconvolution'}:
        raise ValidationError(message='此类资产不支持工作表和列映射。')
    source = PathAccessService.validate_read_path(asset.storage_path)
    before = source.stat()
    schema = inspect_table_schema(source, options.get('sheet_name'))
    if schema['requires_sheet_selection']:
        raise ValidationError(message='文件包含多个工作表，请明确选择数据工作表。')
    columns = schema['columns']
    if any(not column.strip() for column in columns) or len(set(columns)) != len(columns):
        raise ValidationError(message='表头包含空列名或重复列名，请先修正原始文件。')
    identifier = options.get('identifier_column')
    if not isinstance(identifier,str) or identifier not in columns:
        raise ValidationError(message='请选择样本编号列或基因编号列。')
    batch_field = options.get('batch_field')
    if batch_field is not None and not isinstance(batch_field, str):
        raise ValidationError(message='请选择有效的样本批次字段。')
    batch_field = (batch_field or '').strip() or None
    if batch_field and (kind != 'profile' or batch_field not in columns or batch_field == identifier):
        raise ValidationError(message='批次字段仅用于样本指标表，且必须是与样本编号列不同的实际数据列。')
    sample_mappings = normalize_sample_mappings(options.get('sample_mappings'), batch_field)
    canonical = 'Gene' if kind == 'transcriptome' else 'sample'
    orientation = str(options.get('orientation') or 'genes_are_rows') if kind == 'transcriptome' else 'genes_are_rows'
    if kind == 'transcriptome' and orientation not in {'genes_are_rows', 'samples_are_rows'}:
        raise ValidationError(message='请选择有效的转录组矩阵方向。')
    if kind == 'transcriptome' and orientation == 'genes_are_rows' and identifier.strip().casefold() in {
        name.casefold() for name in SAMPLE_COLUMNS
    }:
        raise ValidationError(
            message='该列看起来是样本编号。若样本在行、基因在列，请选择“样本为行、基因为列”；否则请选择基因编号列。'
        )
    if canonical in columns and identifier != canonical and orientation != 'samples_are_rows':
        raise ValidationError(message='目标标准列名已存在，请核对编号列。')
    from flask_app.models.database import Project
    from flask_app.services.project_storage_paths import project_data_dir
    project_root = project_data_dir(db.session.get(Project, asset.project_id), projects_root)
    destination = (project_root / 'prepared_inputs' / (uuid4().hex + '.csv')).resolve()
    if not destination.is_relative_to(project_root):
        raise ValidationError(message='项目输入目录无效。')
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        write_prepared_table(source, destination, schema, identifier, canonical, orientation, sample_mappings, batch_field)
        quality = validate_analysis_inputs([{'asset_type':kind,'path':str(destination)}], {'batch_field': batch_field})
        source_quality = prepared_source_summary(source, schema, kind, identifier, orientation, quality, batch_field)
        after = source.stat()
        if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
            raise ValidationError(message='整理期间原始文件发生变化，请重试。')
        stat = destination.stat()
        prepared_metadata = {'source_asset_id':asset.id,'source_kind':kind,'sheet_name':schema['selected_sheet'],
                            'identifier_column':identifier}
        if batch_field:
            prepared_metadata['batch_field'] = batch_field
        if sample_mappings:
            prepared_metadata['sample_mappings'] = sample_mappings
        if kind == 'transcriptome':
            prepared_metadata['orientation'] = orientation
        prepared = ProjectAsset(project_id=asset.project_id,asset_type='prepared_input',original_name=destination.name,
            storage_path=str(destination),size=stat.st_size,metadata_json=prepared_metadata)
        import hashlib
        from flask_app.services.input_validation_cache import snapshot
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
        prepared.metadata_json = {**prepared.metadata_json, "content_version": digest.hexdigest(), "upload_snapshot": snapshot(destination)}
        db.session.add(prepared);db.session.flush()
        mapping={'prepared_asset_id':prepared.id,'source_size':before.st_size,'source_mtime_ns':before.st_mtime_ns,
                 'prepared_size':stat.st_size,'prepared_mtime_ns':stat.st_mtime_ns,
                 'sheet_name':schema['selected_sheet'],'identifier_column':identifier}
        if batch_field:
            mapping['batch_field'] = batch_field
        if sample_mappings:
            mapping['sample_mappings'] = sample_mappings
        if kind == 'transcriptome':
            mapping['orientation'] = orientation
        asset.metadata_json={**(asset.metadata_json or {}),'input_preparation':mapping,
                             'validation': {'status':'valid', 'prepared_asset_id':prepared.id, 'summary':source_quality}}
        db.session.commit()
        return mapping
    except Exception:
        db.session.rollback()
        destination.unlink(missing_ok=True)
        raise


def write_prepared_table(source, destination, schema, identifier, canonical, orientation='genes_are_rows', sample_mappings=None, batch_field=None):
    """Bound text-table batches by width; retry decoding from an empty output."""
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _CSV_ENCODINGS, _robust_read_csv

    def write_frames(frames):
        mapper = _SampleIdMapping(sample_mappings, batch_field)
        with destination.open('w', encoding='utf-8', newline='') as output:
            first = True
            for frame in frames:
                frame = frame.rename(columns={identifier: canonical})
                # PEP and other script-derived readers consume sample IDs in the first column.
                frame = frame[[canonical] + [name for name in frame.columns if name != canonical]]
                if canonical == 'Gene':
                    if mapper.lookup:
                        mapped = [canonical, *mapper.rewrite(frame.columns[1:])]
                        if len(set(mapped)) != len(mapped):
                            raise ValidationError(message='映射后的样本列编号重复或与基因编号列重名，请修改对应关系。')
                        frame.columns = mapped
                elif mapper.lookup:
                    frame[canonical] = mapper.rewrite(frame[canonical], frame[batch_field] if batch_field else None)
                frame.to_csv(output, index=False, header=first)
                first = False
        mapper.check_sources()

    if canonical == 'Gene' and orientation == 'samples_are_rows':
        write_transposed_expression_table(source, destination, schema, identifier, sample_mappings)
        return
    options = {'dtype': str, 'keep_default_na': False}
    if source.suffix.lower() in {'.xlsx', '.xlsm'}:
        write_frames(iter_workbook_frames(source, schema))
        return
    if source.suffix.lower() == '.xls':
        # The legacy binary format retains its existing reader.
        options['sheet_name'] = schema['selected_sheet']
        write_frames([_robust_read_csv(source, **options)])
        return
    options['sep'] = '\t' if source.suffix.lower() == '.tsv' else ','
    batch_rows = max(1, min(5000, 250000 // max(1, len(schema['columns']))))
    for encoding in dict.fromkeys([*_CSV_ENCODINGS, 'latin-1']):
        try:
            with pd.read_csv(source, encoding=encoding, chunksize=batch_rows, **options) as reader:
                write_frames(reader)
            return
        except UnicodeError:
            continue
    raise ValidationError(message='无法解析输入文件编码，请转换为中文兼容的文本表格后重试。')



def write_transposed_expression_table(source, destination, schema, sample_column, sample_mappings=None):
    """Transpose sample-row expression input with disk-backed float storage."""
    import csv
    import math
    import struct
    import tempfile
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _CSV_ENCODINGS, _robust_read_csv

    columns = [str(column) for column in schema['columns']]
    sample_index = columns.index(sample_column)
    gene_columns = [column for column in columns if column != sample_column]
    gene_indexes = [index for index, column in enumerate(columns) if column != sample_column]
    if not gene_columns:
        raise ValidationError(message='转录组矩阵没有基因数值列。')
    cell = struct.Struct('<d')

    def transpose_frames(frames):
        mapper = _SampleIdMapping(sample_mappings)
        sample_ids = []
        seen = set()
        with tempfile.TemporaryFile(mode='w+b', dir=destination.parent) as spool:
            for frame in frames:
                for row_number, row in enumerate(frame.itertuples(index=False, name=None), start=1):
                    if len(row) != len(columns):
                        raise ValidationError(message=f'转录组第 {row_number} 行字段数与表头不一致。')
                    sample = str(row[sample_index]).strip()
                    if not sample:
                        raise ValidationError(message=f'转录组第 {row_number} 行样本编号为空。')
                    sample = mapper.rewrite([sample])[0]
                    if sample == 'Gene' or sample in seen:
                        raise ValidationError(message=f'转录组样本编号重复或与基因编号列重名：{sample}。')
                    seen.add(sample)
                    sample_ids.append(sample)
                    for index, gene in zip(gene_indexes, gene_columns):
                        raw = str(row[index]).strip()
                        try:
                            value = float(raw)
                        except (ValueError, TypeError, OverflowError) as exc:
                            raise ValidationError(message=f'转录组样本 {sample} 的基因 {gene} 不是有效数值。') from exc
                        if not math.isfinite(value):
                            raise ValidationError(message=f'转录组样本 {sample} 的基因 {gene} 不是有限数值。')
                        spool.write(cell.pack(value))
            mapper.check_sources()
            if not sample_ids:
                raise ValidationError(message='转录组矩阵没有样本数据行。')
            with destination.open('w', encoding='utf-8', newline='') as output:
                writer = csv.writer(output, lineterminator='\n')
                writer.writerow(['Gene', *sample_ids])
                for gene_index, gene in enumerate(gene_columns):
                    values = []
                    for sample_index_in_data in range(len(sample_ids)):
                        offset = (sample_index_in_data * len(gene_columns) + gene_index) * cell.size
                        spool.seek(offset)
                        packed = spool.read(cell.size)
                        if len(packed) != cell.size:
                            raise OSError('整理后的转录组临时矩阵不完整。')
                        values.append(repr(cell.unpack(packed)[0]))
                    writer.writerow([gene, *values])

    suffix = source.suffix.lower()
    if suffix in {'.xlsx', '.xlsm'}:
        transpose_frames(iter_workbook_frames(source, schema))
        return
    if suffix == '.xls':
        options = {'dtype': str, 'keep_default_na': False, 'sheet_name': schema['selected_sheet']}
        transpose_frames([_robust_read_csv(source, **options)])
        return
    options = {'dtype': str, 'keep_default_na': False}
    if suffix == '.tsv':
        options['sep'] = '\t'
    batch_rows = max(1, min(5000, 250000 // max(1, len(columns))))
    for encoding in dict.fromkeys([*_CSV_ENCODINGS, 'latin-1']):
        try:
            with pd.read_csv(source, encoding=encoding, chunksize=batch_rows, **options) as reader:
                transpose_frames(reader)
            return
        except UnicodeError:
            destination.unlink(missing_ok=True)
    raise ValidationError(message='无法解析转录组文件编码，请转换为中文兼容的文本表格后重试。')


def iter_workbook_frames(source, schema):
    """Read the selected worksheet with bounded row batches and cached formula values."""
    import pandas as pd
    from openpyxl import load_workbook

    columns = schema['columns']
    batch_rows = max(1, min(5000, 250000 // max(1, len(columns))))
    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook[schema['selected_sheet']]
        sheet.reset_dimensions()
        rows = sheet.iter_rows()
        next(rows, None)
        batch, pending_empty = [], 0
        for cells in rows:
            values = []
            for cell in cells:
                value = cell.value
                if value is None or cell.data_type == 'e':
                    value = ''
                elif cell.data_type == 'n' and isinstance(value, float) and value.is_integer():
                    value = int(value)
                values.append(str(value))
            if any(value != '' for value in values[len(columns):]):
                raise ValidationError(message='工作表数据超出表头列数，请补齐列名后重试。')
            values = values[:len(columns)] + [''] * max(0, len(columns) - len(values))
            if not any(values):
                pending_empty += 1
                continue
            # Retain interior empty rows, but omit worksheet formatting after the data.
            while pending_empty:
                batch.append([''] * len(columns))
                pending_empty -= 1
                if len(batch) >= batch_rows:
                    yield pd.DataFrame(batch, columns=columns)
                    batch = []
            batch.append(values)
            if len(batch) >= batch_rows:
                yield pd.DataFrame(batch, columns=columns)
                batch = []
        if batch:
            yield pd.DataFrame(batch, columns=columns)
        else:
            yield pd.DataFrame(columns=columns)
    finally:
        workbook.close()


def revalidate_prepared_sources(job):
    for ref in (job.get('payload') or {}).get('source_assets', []):
        asset = db.session.get(ProjectAsset, ref.get('asset_id'))
        if not asset:
            raise ValidationError(message='任务输入资产已删除，请重新选择数据。')
        current = analysis_input_path(asset)
        if Path(current).resolve() != Path(ref['path']).resolve():
            raise ValidationError(message='任务输入映射已改变，请重新提交分析。')


def reset_input_preparation(asset):
    metadata = dict(asset.metadata_json or {})
    previous = metadata.pop('input_preparation', None)
    if previous is not None:
        metadata['validation'] = {'status':'pending'}
        asset.metadata_json = metadata
        db.session.commit()
        from flask_app.services.input_validation_cache import schedule_uploaded_validation
        schedule_uploaded_validation([asset])
    # Registered prepared assets remain available for provenance and lifecycle cleanup.
    return previous is not None
