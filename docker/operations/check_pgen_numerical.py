from pathlib import Path
import tempfile
import pandas as pd
from flask_app.services.pgen_analysis_service import PgenAnalysisService
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    pep=root/'pep';pep.mkdir()
    pd.DataFrame({'CDR3(pep)':['CASSIRSSYEQYF'],'V':['TRBV19'],'J':['TRBJ2-7']}).to_csv(pep/'S1_TRB.csv',index=False)
    pd.DataFrame({'sample':['S1'],'group':['A']}).to_csv(root/'profile.csv',index=False)
    report=PgenAnalysisService(output_parent=root/'out').generate_report(pep_data_dir=str(pep),profile_path=str(root/'profile.csv'),selected_chains=['TRB'])
    detail=list((root/'out').rglob('TRB.csv'))
    assert len(detail)==1
    probability=float(pd.read_csv(detail[0])['Pgen'].iloc[0])
    assert abs(probability-1.9603935768649733e-7)<1e-15
    print('Pgen report numerical acceptance:',probability)
