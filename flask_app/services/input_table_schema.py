"""Inspect original headers and sheets before an explicit input mapping."""
from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService


def inspect_table_schema(value, sheet_name=None):
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    path = PathAccessService.validate_read_path(str(value))
    sheets = []
    selected = None
    if path.suffix.lower() in {'.xlsx', '.xls', '.xlsm'}:
        with pd.ExcelFile(path) as workbook:
            sheets = workbook.sheet_names
        selected = sheet_name if sheet_name is not None else (sheets[0] if sheets else None)
        if selected not in sheets:
            raise ValidationError(message='所选工作表不存在，请重新选择。')
    elif sheet_name is not None:
        raise ValidationError(message='文本表格不支持选择工作表。')
    options = {'header': None, 'nrows': 6, 'dtype': str, 'keep_default_na': False}
    if selected is not None: options['sheet_name'] = selected
    if path.suffix.lower() == '.tsv': options['sep'] = '\t'
    frame = _robust_read_csv(path, **options)
    if frame.empty:
        if sheets:
            return {'sheets':sheets,'selected_sheet':selected,'columns':[], 'preview_rows':[], 'preview_limit':5,'requires_sheet_selection':len(sheets)>1 and sheet_name is None}
        raise ValidationError(message='所选表格为空。')
    # Read header as data so duplicate names and leading zeroes remain visible.
    rows = frame.fillna('').astype(str).values.tolist()
    return {'sheets': sheets, 'selected_sheet': selected, 'columns': rows[0], 'preview_rows': rows[1:],
            'preview_limit': 5, 'requires_sheet_selection': len(sheets) > 1 and sheet_name is None}
