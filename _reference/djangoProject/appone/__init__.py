
from contextlib import contextmanager
from appone.constant import DBURL
import pymongo


@contextmanager
def mongodb_client_factory():
    client = pymongo.MongoClient(DBURL, maxidletimems=1200)
    try:
        yield client
    finally:
        client.close()
