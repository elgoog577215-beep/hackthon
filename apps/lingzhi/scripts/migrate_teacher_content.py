#!/usr/bin/env python3
"""Run offline with --mode preflight|apply|verify and an explicit data directory."""
import argparse
import json
import os
from pathlib import Path
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir',type=Path,required=True)
parser.add_argument('--mode',choices=['preflight','apply','verify'],default='preflight')
parser.add_argument('--backup-dir',type=Path)
parser.add_argument('--course-id',action='append')
parser.add_argument('--require-teacher-bodies',action='store_true',help='Refuse activation while teacher revisions still reference the retired body store')
args=parser.parse_args()
# Must precede backend imports. Read-only modes never instantiate Storage.
os.environ['LINGZHI_DATA_DIR']=str(args.data_dir.resolve())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from teacher_content_migration import migrate
report=migrate(args.data_dir,mode=args.mode,backup_dir=args.backup_dir,course_ids=args.course_id)
print(json.dumps(report,ensure_ascii=False,indent=2))
sys.exit(1 if any(c['status'] in {'conflict','not_migrated'} or (args.require_teacher_bodies and c.get('reference_revisions')) for c in report['courses']) else 0)
