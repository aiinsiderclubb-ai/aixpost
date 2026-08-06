import os
from rq import Queue, SimpleWorker
import redis


def main():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    kwargs = {}
    if redis_url.startswith('rediss://'):
        kwargs['ssl_cert_reqs'] = None
    conn = redis.from_url(redis_url, **kwargs)
    conn.ping()
    names = [
        n.strip()
        for n in (os.environ.get('RQ_QUEUES') or 'default').split(',')
        if n.strip()
    ]
    queues = [Queue(name, connection=conn) for name in names]
    print(f"RQ worker listening on queues={names} redis={redis_url.split('@')[-1]}")
    SimpleWorker(queues, connection=conn).work()


if __name__ == '__main__':
    main()
