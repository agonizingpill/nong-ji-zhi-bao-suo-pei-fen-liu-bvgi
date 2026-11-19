import json,os
from pathlib import Path
from .risk_model import assess
from .claim_service import current_epoch

def score_claim(s,c):
    c.risk,metrics,coverage,reason=assess(s,c)
    c.coverage=coverage;c.review_reason=reason;c.review_basis='';c.score_epoch=current_epoch(s).epoch
    c.status='assessed';c.assessment_note=json.dumps(metrics,ensure_ascii=False)
    art=Path(os.getenv('ARTIFACTS_DIR','/artifacts'))
    (art/f'claim-{c.id}-model.json').write_text(json.dumps(metrics))
