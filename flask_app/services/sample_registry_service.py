"""
Project sample registry service.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

import pandas as pd
from sqlalchemy import or_

from flask_app.exceptions import SampleRecordChangedError, ValidationError
from flask_app.models.database import Project, SampleRecord, db
from flask_app.services.user_scope import assert_owned, scope_query


def _normalize_column_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


class SampleRegistryService:
    """Import and query project sample metadata."""

    COLUMN_ALIASES = {
        'sample_id': {'sampleid', 'id'},
        'sample_name': {'samplename', 'sample', 'name'},
        'sequence_id': {'sequenceid', 'sequence'},
        'spices': {'spices', 'species'},
        'institution': {'institution'},
        'chain_flag': {'chainflag', 'chain'},
        'is_healthy': {'ishealthy', 'healthy'},
        'illness': {'illness', 'disease'},
        'is_pe': {'ispe', 'pe'},
        'contain_method': {'containmethod', 'method'},
        'iso_tag': {'isotag', 'isotype', 'tag'},
    }

    def sample_query(
        self,
        *,
        project_id: str = "",
        asset_set: str = "",
        sample_id: str = "",
        input_sample_id: str = "",
        sample_name: str = "",
        search: str = "",
        project_name: str = "",
        institution: str = "",
        sequence_id: str = "",
        contain_method: str = "",
        iso_tag: str = "",
        spices: Iterable[str] | None = None,
        chain_flag: Iterable[str] | None = None,
        is_healthy: str = "",
        illness: Iterable[str] | None = None,
        is_pe: str = "",
    ):
        query = SampleRecord.query.join(Project).order_by(SampleRecord.created_at.desc())
        query = scope_query(query, Project)

        if search.strip():
            term = search.strip()
            query = query.filter(or_(SampleRecord.sample_id.icontains(term, autoescape=True),
                                     SampleRecord.sample_name.icontains(term, autoescape=True),
                                     Project.name.icontains(term, autoescape=True)))
        if project_id:
            query = query.filter(SampleRecord.project_id == project_id)
        if asset_set:
            query = query.filter(SampleRecord.extra_metadata["asset_set"].as_string() == asset_set)
        if sample_id:
            query = query.filter(SampleRecord.sample_id.ilike(f"%{sample_id.strip()}%"))
        if sample_name:
            query = query.filter(SampleRecord.sample_name.ilike(f"%{sample_name.strip()}%"))
        if project_name:
            query = query.filter(Project.name.ilike(f"%{project_name.strip()}%"))
        if institution:
            query = query.filter(SampleRecord.institution.ilike(f"%{institution.strip()}%"))
        if sequence_id:
            query = query.filter(SampleRecord.sequence_id.ilike(f"%{sequence_id.strip()}%"))
        if contain_method:
            query = query.filter(SampleRecord.contain_method.ilike(f"%{contain_method.strip()}%"))
        if iso_tag:
            query = query.filter(SampleRecord.iso_tag.ilike(f"%{iso_tag.strip()}%"))
        if is_healthy:
            query = query.filter(SampleRecord.is_healthy == is_healthy.strip())
        if is_pe:
            query = query.filter(SampleRecord.is_pe == is_pe.strip())

        def _apply_multi(query_obj, column, values):
            cleaned = [str(value).strip() for value in (values or []) if str(value).strip()]
            if cleaned:
                query_obj = query_obj.filter(column.in_(cleaned))
            return query_obj

        species_aliases = [
            {'human', '人', '人类', 'homo sapiens'},
            {'mouse', '小鼠', 'mus musculus'},
            {'other', '其他'},
        ]
        species_values = set()
        for raw in spices or []:
            value = str(raw).strip().lower()
            if value:
                species_values.update(next((aliases for aliases in species_aliases if value in aliases), {value}))
        if species_values:
            from sqlalchemy import func
            query = query.filter(func.lower(func.trim(SampleRecord.spices)).in_(species_values))
        query = _apply_multi(query, SampleRecord.chain_flag, chain_flag)
        query = _apply_multi(query, SampleRecord.illness, illness)
        if input_sample_id:
            if not project_id or not asset_set:
                raise ValidationError(message='核对输入编号时请同时指定项目和数据集。')
            identifiers = []
            candidates = query.filter(or_(SampleRecord.sample_id == input_sample_id,
                SampleRecord.extra_metadata['input_sample_id'].as_string() == input_sample_id))
            for identifier, original, metadata in candidates.with_entities(
                    SampleRecord.id, SampleRecord.sample_id, SampleRecord.extra_metadata).yield_per(100):
                if (metadata or {}).get('input_sample_id', original) == input_sample_id:
                    identifiers.append(identifier)
            query = query.filter(SampleRecord.id.in_(identifiers))
        return query

    def list_samples(self, *, page: int | None = None, page_size: int = 50, **filters):
        query = self.sample_query(**filters)
        if page is not None:
            total = query.count()
            rows = query.order_by(SampleRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
            return rows, {'page': page, 'page_size': page_size, 'total': total,
                          'total_pages': (total + page_size - 1) // page_size if total else 0}
        return query.all()

    def get_sample(self, sample_record_id: str) -> SampleRecord:
        sample = SampleRecord.query.get(sample_record_id)
        if sample is None:
            raise ValidationError(message="Sample record not found", details={'sample_id': sample_record_id})
        assert_owned(sample.project, 'Project')
        return sample

    def remove_source_records(self, project_id: str, source_asset_id: str) -> None:
        # Unknown historical provenance never authorizes a project-wide delete.
        records = SampleRecord.query.filter(
            SampleRecord.project_id == project_id,
            SampleRecord.extra_metadata['source_asset_id'].as_string() == source_asset_id,
        ).all()
        for record in records:
            metadata = dict(record.extra_metadata or {})
            if metadata.get('manual_fields') or metadata.get('registration_kind') == 'manual':
                metadata.pop('source_asset_id', None)
                metadata['registration_kind'] = 'manual'
                record.extra_metadata = metadata
            else:
                db.session.delete(record)

    def replace_project_samples(self, project: Project, rows: List[Dict[str, object]], *, commit: bool = True,
                                source_asset_id: str = '', asset_set: str = 'Set1',
                                replace_existing: bool = True) -> List[SampleRecord]:
        if not source_asset_id:
            # Legacy direct callers retain their explicit replacement contract.
            SampleRecord.query.filter(SampleRecord.project_id == project.id).delete()
            previous = []
        else:
            previous = SampleRecord.query.filter(
                SampleRecord.project_id == project.id,
                SampleRecord.extra_metadata['asset_set'].as_string() == asset_set,
                SampleRecord.extra_metadata['source_asset_id'].as_string().isnot(None),
            ).all() if replace_existing else []
        available = {}
        for record in previous:
            available.setdefault(record.sample_id or record.sample_name, []).append(record)
        sample_records = []
        fields = ('sample_id', 'sample_name', 'sequence_id', 'spices', 'institution', 'chain_flag',
                  'is_healthy', 'illness', 'is_pe', 'contain_method', 'iso_tag')
        for row in rows:
            name = str(row.get('sample_name') or '').strip()
            if not name:
                continue
            identifier = self._nullable(row.get('sample_id'))
            candidates = available.get(identifier or name, [])
            record = candidates.pop(0) if len(candidates) == 1 else None
            if record is not None:
                previous.remove(record)
            else:
                record = SampleRecord(project_id=project.id, sample_name=name)
                db.session.add(record)
            original = dict(record.extra_metadata or {})
            manual = set(original.get('manual_fields') or [])
            for field in fields:
                if field not in manual:
                    value = name if field == 'sample_name' else self._nullable(row.get(field))
                    if field == 'institution':
                        value = value or project.institution
                    setattr(record, field, value)
            metadata = {**original, **(row.get('extra_metadata') or {})}
            if source_asset_id:
                metadata.update(source_asset_id=source_asset_id, asset_set=asset_set, registration_kind='imported')
            record.extra_metadata = metadata
            sample_records.append(record)
        for record in previous:
            metadata = dict(record.extra_metadata or {})
            if metadata.get('manual_fields'):
                metadata.pop('source_asset_id', None)
                metadata['registration_kind'] = 'manual'
                record.extra_metadata = metadata
            else:
                db.session.delete(record)
        if commit:
            db.session.commit()
        return sample_records

    def import_sample_summary_dataframe(self, project: Project, df: pd.DataFrame, *, commit: bool = True, source_asset_id: str = '', asset_set: str = 'Set1', replace_existing: bool = True) -> List[SampleRecord]:
        if df.empty:
            raise ValidationError(message="Sample summary file is empty")

        normalized_columns = {_normalize_column_name(col): col for col in df.columns}

        def resolve_column(field_name: str) -> Optional[str]:
            for alias in self.COLUMN_ALIASES.get(field_name, set()):
                if alias in normalized_columns:
                    return normalized_columns[alias]
            return None

        column_map = {field_name: resolve_column(field_name) for field_name in self.COLUMN_ALIASES}
        if not column_map['sample_name']:
            raise ValidationError(
                message="Sample summary must contain a sample name column",
                details={'required_field': 'sample_name', 'columns': list(df.columns)},
            )

        rows: List[Dict[str, object]] = []
        for _, row in df.iterrows():
            parsed: Dict[str, object] = {}
            used_columns = set()
            for field_name, source_col in column_map.items():
                if source_col:
                    value = row.get(source_col)
                    parsed[field_name] = self._normalize_cell(value)
                    used_columns.add(source_col)

            extra_metadata = {}
            for col in df.columns:
                if col in used_columns:
                    continue
                extra_metadata[col] = self._normalize_cell(row.get(col))
            parsed['extra_metadata'] = extra_metadata
            rows.append(parsed)

        return self.replace_project_samples(project, rows, commit=commit, source_asset_id=source_asset_id, asset_set=asset_set, replace_existing=replace_existing)

    def update_sample(self, sample: SampleRecord, payload: Dict[str, object], *, input_sample_id: str | None = None) -> SampleRecord:
        # Existing import/batch operations lock the project; use the same ordering.
        with db.session.no_autoflush:
            db.session.query(Project).filter_by(id=sample.project_id).with_for_update().one()
            if sample.id and sample not in db.session.new:
                current = SampleRecord.query.filter_by(id=sample.id).populate_existing().with_for_update().first()
                if current is None:
                    raise ValidationError(message='此登记已移除，请重新读取样本列表。')
                sample = current
        if 'sample_id' in payload and self._nullable(payload.get('sample_id')) != sample.sample_id:
            raise ValidationError(message='原始样本编号不能通过补充登记修改。')
        editable_fields = [
            'sample_id', 'sample_name', 'sequence_id', 'spices', 'institution',
            'chain_flag', 'is_healthy', 'illness', 'is_pe', 'contain_method', 'iso_tag',
        ]
        expected = payload.get('expected_values')
        if 'expected_values' in payload:
            submitted = set(payload) & set(editable_fields)
            if (not isinstance(expected, dict) or set(expected) != submitted
                    or any(value is not None and not isinstance(value, str) for value in expected.values())):
                raise ValidationError(message='请携带本次修改字段的原值，重新读取后再保存。')
            conflicts = {}
            for field_name in submitted:
                original = self._nullable(expected[field_name])
                latest = self._nullable(getattr(sample, field_name))
                if original != latest:
                    conflicts[field_name] = {'expected': original, 'current': latest,
                                             'submitted': self._nullable(payload[field_name])}
            if conflicts:
                raise SampleRecordChangedError(details={'conflicts': conflicts, 'sample': sample.to_dict()})
        changed = set()
        for field_name in editable_fields:
            if field_name not in payload:
                continue
            value = self._nullable(payload.get(field_name))
            if value != getattr(sample, field_name):
                changed.add(field_name)
                setattr(sample, field_name, value)

        if 'extra_metadata' in payload and isinstance(payload.get('extra_metadata'), dict):
            system = {key: value for key, value in (sample.extra_metadata or {}).items()
                      if key in {'source_asset_id', 'asset_set', 'registration_kind', 'manual_fields', 'input_sample_id', 'unmatched_input', 'registration_receipt'}}
            sample.extra_metadata = {**(payload.get('extra_metadata') or {}), **system}

        if input_sample_id is not None:
            metadata = {**(sample.extra_metadata or {}), 'input_sample_id': input_sample_id}
            metadata.pop('unmatched_input', None)
            sample.extra_metadata = metadata

        if changed:
            metadata = dict(sample.extra_metadata or {})
            metadata['manual_fields'] = sorted(set(metadata.get('manual_fields') or []) | changed)
            sample.extra_metadata = metadata

        if not str(sample.sample_name or '').strip():
            raise ValidationError(message="Sample name is required", details={'field': 'sample_name'})

        db.session.commit()
        return sample

    def get_distinct_field_values(
        self,
        *,
        project_id: str = "",
        asset_set: str = "",
        field_name: str = "",
        include_identifiers: bool = True,
    ) -> Dict[str, List[str]]:
        allowed_fields = {
            'project_name',
            'sample_id',
            'sequence_id',
            'institution',
            'spices',
            'chain_flag',
            'is_healthy',
            'illness',
            'is_pe',
            'contain_method',
            'iso_tag',
        }

        base_query = SampleRecord.query.join(Project)
        base_query = scope_query(base_query, Project)
        if project_id:
            base_query = base_query.filter(SampleRecord.project_id == project_id)

        if asset_set:
            base_query = base_query.filter(SampleRecord.extra_metadata["asset_set"].as_string() == asset_set)

        def _collect(values):
            cleaned = sorted({str(value).strip() for value in values if str(value or '').strip()})
            return cleaned

        def _project_names():
            return _collect(row[0] for row in base_query.with_entities(Project.name).distinct().all())

        field_map = {
            'project_name': _project_names,
            'sample_id': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.sample_id).distinct().all()),
            'sequence_id': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.sequence_id).distinct().all()),
            'institution': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.institution).distinct().all()),
            'spices': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.spices).distinct().all()),
            'chain_flag': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.chain_flag).distinct().all()),
            'is_healthy': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.is_healthy).distinct().all()),
            'illness': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.illness).distinct().all()),
            'is_pe': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.is_pe).distinct().all()),
            'contain_method': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.contain_method).distinct().all()),
            'iso_tag': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.iso_tag).distinct().all()),
        }

        if not include_identifiers:
            field_map = {name: resolver for name, resolver in field_map.items()
                         if name not in {'sample_id', 'sequence_id'}}
            if field_name in {'sample_id', 'sequence_id'}:
                raise ValidationError(message='编号候选请使用搜索分页方式读取。')

        if field_name:
            if field_name not in allowed_fields:
                raise ValidationError(message="Unsupported sample field", details={'field': field_name})
            return {field_name: field_map[field_name]()}

        return {name: resolver() for name, resolver in field_map.items()}

    @staticmethod
    def _normalize_cell(value):
        if pd.isna(value):
            return None
        return str(value).strip()

    @staticmethod
    def _nullable(value):
        cleaned = str(value or '').strip()
        return cleaned or None


_sample_registry_service = SampleRegistryService()


def get_sample_registry_service() -> SampleRegistryService:
    return _sample_registry_service
