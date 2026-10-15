"""Load one GPU model, exercise the shared service, and evaluate a validation DB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from .environment import snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/validation-v2.db')
    parser.add_argument('--output', default='reports/benchmark.json')
    args = parser.parse_args()
    path = Path(args.db)
    if not path.is_file():
        parser.error('검증 DB를 먼저 생성하세요.')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), environment=snapshot(),
                  db=str(path), db_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in Path(__file__).parent.glob('*.py')})
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        report['data_groups'] = con.execute('SELECT reign,year,COUNT(*) FROM records GROUP BY reign,year ORDER BY reign,year').fetchall()
    finally:
        con.close()
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    try:
        # Unsloth must be imported before torch/transformers for its patches.
        from .model import TextToSQL, MODEL_ID, MODEL_REVISION
        print('모델 로딩 시작', flush=True)
        start = time.monotonic()
        model = TextToSQL()
        report['model_load_sec'] = round(time.monotonic() - start, 4)
        report['model_id'] = MODEL_ID
        report['requested_adapter_revision'] = os.environ.get('SILOK_MODEL_REVISION') or MODEL_REVISION
        import torch
        report['torch_cuda'] = torch.version.cuda
        report['gpu_name'] = torch.cuda.get_device_name()
        report['model_config_commit'] = getattr(model.model.config, '_commit_hash', None)
        report['adapters'] = {name: config.to_dict() for name, config in getattr(model.model, 'peft_config', {}).items()}
        # Convert sets/enums in PEFT config without dumping weights or credentials.
        report['adapters'] = json.loads(json.dumps(report['adapters'], default=lambda value: sorted(value) if isinstance(value, set) else str(value)))
        report['load_peak_allocated_mib'] = round(torch.cuda.max_memory_allocated()/1024**2, 2)
        report['load_peak_reserved_mib'] = round(torch.cuda.max_memory_reserved()/1024**2, 2)
        torch.cuda.reset_peak_memory_stats()
        from .service import QuestionService
        service = QuestionService(path, lambda: model)
        report['smoke'] = service.ask('전체 기사는 몇 건인가요?').to_dict()
        save()
        from .evaluate import evaluate
        report['evaluation'] = evaluate(path, output.with_name(output.stem + '-evaluation.json'), model=model)
        report['correct'] = sum(item['correct'] for item in report['evaluation'])
        report['inference_peak_allocated_mib'] = round(torch.cuda.max_memory_allocated()/1024**2, 2)
        report['inference_peak_reserved_mib'] = round(torch.cuda.max_memory_reserved()/1024**2, 2)
        report['status'] = 'complete'
    except Exception as exc:
        report.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    print('보고서:', output)


if __name__ == '__main__':
    main()
