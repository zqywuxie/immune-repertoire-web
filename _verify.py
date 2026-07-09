import py_compile
try:
    py_compile.compile('flask_app/routes/api_script_hub.py', doraise=True)
    print('api_script_hub.py: syntax OK')
except py_compile.PyCompileError as e:
    print(f'SYNTAX ERROR: {e}')

with open('flask_app/static/js/script_hub.js', 'r') as f:
    js = f.read()
b = js.count('{') - js.count('}')
p = js.count('(') - js.count(')')
print(f'script_hub.js: braces={b} parens={p}, size={len(js)}')

with open('flask_app/routes/api_script_hub.py', 'r') as f:
    py = f.read()

features = {
    'profile in ALLOWED_MODULES': '"profile"' in py,
    '_write_unified_viewer': 'def _write_unified_viewer(' in py,
    '_build_and_save_viewer': 'def _build_and_save_viewer(' in py,
    'inspect_volcano fixed': 'search_dir = data_dir or base_path' in py,
    'inspect_umapin fixed': 'df_VJ_all.csv' in py,
    'inspect_umap fixed': 'pd.read_csv(dp, nrows=0)' in py,
    'inspect_topclone fixed': '_inspect_data_selection_payload' in py,
    'cached_usage inspect API': 'def inspect_cached_usage_asset' in py,
}
for k, v in features.items():
    print(f'  {k}: {"OK" if v else "MISSING"}')
