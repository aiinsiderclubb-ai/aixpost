import os
from rq import Queue, SimpleWorker
import redis


def main():
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    conn = redis.from_url(redis_url)
    analytics_queue = Queue("analytics", connection=conn)
    print("Analytics worker listening on queue: analytics")
    SimpleWorker([analytics_queue], connection=conn).work()


if __name__ == "__main__":
    main()
