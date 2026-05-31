"""
Project sample registry service.
"""

from __future__ import annotations

import io
import re
from typing import Dict, Iterable, List, Optional

import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, SampleRecord, db


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

    def list_samples(
        self,
        *,
        project_id: str = "",
        sample_id: str = "",
        sample_name: str = "",
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
    ) -> List[SampleRecord]:
        query = SampleRecord.query.join(Project).order_by(SampleRecord.created_at.desc())

        if project_id:
            query = query.filter(SampleRecord.project_id == project_id)
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

        query = _apply_multi(query, SampleRecord.spices, spices)
        query = _apply_multi(query, SampleRecord.chain_flag, chain_flag)
        query = _apply_multi(query, SampleRecord.illness, illness)
        return query.all()

    def get_sample(self, sample_record_id: str) -> SampleRecord:
        sample = SampleRecord.query.get(sample_record_id)
        if sample is None:
            raise ValidationError(message="Sample record not found", details={'sample_id': sample_record_id})
        return sample

    def replace_project_samples(self, project: Project, rows: List[Dict[str, object]]) -> List[SampleRecord]:
        SampleRecord.query.filter(SampleRecord.project_id == project.id).delete()

        sample_records: List[SampleRecord] = []
        for row in rows:
            sample_name = str(row.get('sample_name') or '').strip()
            if not sample_name:
                continue

            sample_record = SampleRecord(
                project_id=project.id,
                sample_id=self._nullable(row.get('sample_id')),
                sample_name=sample_name,
                sequence_id=self._nullable(row.get('sequence_id')),
                spices=self._nullable(row.get('spices')),
                institution=self._nullable(row.get('institution') or project.institution),
                chain_flag=self._nullable(row.get('chain_flag')),
                is_healthy=self._nullable(row.get('is_healthy')),
                illness=self._nullable(row.get('illness')),
                is_pe=self._nullable(row.get('is_pe')),
                contain_method=self._nullable(row.get('contain_method')),
                iso_tag=self._nullable(row.get('iso_tag')),
                extra_metadata=row.get('extra_metadata') or {},
            )
            db.session.add(sample_record)
            sample_records.append(sample_record)

        db.session.commit()
        return sample_records

    def import_sample_summary_dataframe(self, project: Project, df: pd.DataFrame) -> List[SampleRecord]:
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

        return self.replace_project_samples(project, rows)

    def update_sample(self, sample: SampleRecord, payload: Dict[str, object]) -> SampleRecord:
        editable_fields = [
            'sample_id', 'sample_name', 'sequence_id', 'spices', 'institution',
            'chain_flag', 'is_healthy', 'illness', 'is_pe', 'contain_method', 'iso_tag',
        ]
        for field_name in editable_fields:
            if field_name not in payload:
                continue
            setattr(sample, field_name, self._nullable(payload.get(field_name)))

        if 'extra_metadata' in payload and isinstance(payload.get('extra_metadata'), dict):
            sample.extra_metadata = payload.get('extra_metadata') or {}

        if not str(sample.sample_name or '').strip():
            raise ValidationError(message="Sample name is required", details={'field': 'sample_name'})

        db.session.commit()
        return sample

    def get_distinct_field_values(
        self,
        *,
        project_id: str = "",
        field_name: str = "",
    ) -> Dict[str, List[str]]:
        allowed_fields = {
            'project_name',
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
        if project_id:
            base_query = base_query.filter(SampleRecord.project_id == project_id)

        def _collect(values):
            cleaned = sorted({str(value).strip() for value in values if str(value or '').strip()})
            return cleaned

        def _project_names():
            return _collect(row[0] for row in base_query.with_entities(Project.name).distinct().all())

        field_map = {
            'project_name': _project_names,
            'institution': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.institution).distinct().all()),
            'spices': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.spices).distinct().all()),
            'chain_flag': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.chain_flag).distinct().all()),
            'is_healthy': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.is_healthy).distinct().all()),
            'illness': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.illness).distinct().all()),
            'is_pe': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.is_pe).distinct().all()),
            'contain_method': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.contain_method).distinct().all()),
            'iso_tag': lambda: _collect(row[0] for row in base_query.with_entities(SampleRecord.iso_tag).distinct().all()),
        }

        if field_name:
            if field_name not in allowed_fields:
                raise ValidationError(message="Unsupported sample field", details={'field': field_name})
            return {field_name: field_map[field_name]()}

        return {name: resolver() for name, resolver in field_map.items()}

    def export_samples_csv(self, samples: List[SampleRecord]) -> io.BytesIO:
        rows = []
        extra_columns = sorted({
            key
            for sample in samples
            for key in (sample.extra_metadata or {}).keys()
        })

        for sample in samples:
            row = {
                'project_id': sample.project_id,
                'project_name': sample.project.name if sample.project else None,
                'sample_id': sample.sample_id,
                'sample_name': sample.sample_name,
                'sequence_id': sample.sequence_id,
                'spices': sample.spices,
                'institution': sample.institution,
                'chain_flag': sample.chain_flag,
                'is_healthy': sample.is_healthy,
                'illness': sample.illness,
                'is_pe': sample.is_pe,
                'contain_method': sample.contain_method,
                'iso_tag': sample.iso_tag,
            }
            for key in extra_columns:
                row[key] = (sample.extra_metadata or {}).get(key)
            rows.append(row)

        df = pd.DataFrame(rows)
        buffer = io.BytesIO()
        buffer.write(df.to_csv(index=False).encode('utf-8-sig'))
        buffer.seek(0)
        return buffer

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
