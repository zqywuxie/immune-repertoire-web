"""Create a consistent SQLite backup, then verify its integrity."""
import argparse
from pathlib import Path
import sqlite3

def backup_database(source, destination):
    source=Path(source).resolve(strict=True);destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Destination must be a new backup file')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        with sqlite3.connect(destination) as backup:
            original.backup(backup)
            result=backup.execute('PRAGMA integrity_check').fetchone()[0]
            if result!='ok':raise RuntimeError('Backup integrity check failed: '+result)
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print('Verified SQLite backup:',backup_database(args.database,args.output))
