import os
from rq import Queue, SimpleWorker
import redis


def main():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    conn = redis.from_url(redis_url)
    q = Queue('default', connection=conn)
    # Use SimpleWorker to avoid fork() crashes with Chrome on macOS
    SimpleWorker([q], connection=conn).work()


if __name__ == '__main__':
    main()



