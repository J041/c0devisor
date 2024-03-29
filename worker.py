import redis

from app import app

listen = ["high", "medium", "low"]

# redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(app.config["REDIS_URL"])
