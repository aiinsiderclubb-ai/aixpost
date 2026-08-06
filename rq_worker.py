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
    q = Queue('default', connection=conn)
    # Use SimpleWorker to avoid fork() crashes with Chrome on macOS / Docker
    print(f"RQ worker listening on queue=default redis={redis_url.split('@')[-1]}")
    SimpleWorker([q], connection=conn).work()


if __name__ == '__main__':
    main()



