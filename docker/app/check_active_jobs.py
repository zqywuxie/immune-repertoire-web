"""Read-only deployment preflight against the running application's database."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

def ensure_idle(connection):
    rows = connection.execute(text("SELECT status, COUNT(*) FROM analysis_jobs WHERE status IN ('queued', 'running') GROUP BY status")).all()
    if rows:
        counts = dict(rows)
        raise SystemExit(f"暂不更新：仍有 {counts.get('running', 0)} 个运行任务、{counts.get('queued', 0)} 个等待任务。请在任务中心等待完成或取消后，再执行 deploy.sh。")

if __name__ == '__main__':
    url = URL.create('mysql+pymysql', username=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
        host=os.environ['MYSQL_HOST'],port=int(os.environ.get('MYSQL_PORT','3306')),database=os.environ['MYSQL_DATABASE'])
    engine = create_engine(url, connect_args={'connect_timeout':10})
    with engine.connect() as connection:
        ensure_idle(connection)
    print('活动任务检查通过。')
