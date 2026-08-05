import os
from rq import Queue
import redis


def test_profile_path_building(tmp_path):
    from bot.group_fetcher import FacebookGroupFetcher
    user_id = 123
    fetcher = FacebookGroupFetcher(username='u', password='p', user_id=user_id, use_session=True, reset_session=True)
    assert f"profile_user_{user_id}" in fetcher.profile_dir
    assert fetcher.cookies_file.endswith('facebook_cookies.json')


def test_rq_queue_env():
    url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    conn = redis.from_url(url)
    q = Queue('default', connection=conn)
    # Queue object can be created
    assert q.name == 'default'



