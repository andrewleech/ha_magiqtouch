import aiohttp
import asyncio
import lru
import os
import yarl


# max # of requests per session
_max_number_sessions = int(os.environ.get("AIOHTTP_SESSION_SIZE", "200"))


def session_purged(key, value):
    asyncio.ensure_future(value.close())


_sessions = lru.LRU(_max_number_sessions, callback=session_purged)
_counts = {}


_connect_options = {
    "ttl_dns_cache": int(os.environ.get("AIOHTTP_SESSION_DNS_CACHE", "20")),
    "limit": int(os.environ.get("AIOHTTP_SESSION_LIMIT", "500")),
    "force_close": True,
    "enable_cleanup_closed": True,
}


def get_session(url):
    url = yarl.URL(url)
    if url.host not in _sessions:
        _sessions[url.host] = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(**_connect_options)
        )
        _counts[url.host] = 0
    _counts[url.host] += 1
    return _sessions[url.host]


async def close():
    for session in _sessions.values():
        await session.close()
    _sessions.clear()
    _counts.clear()


def post(url, *args, **kwargs):
    session = get_session(url)
    return session.post(url, *args, **kwargs)


def get(url, *args, **kwargs):
    session = get_session(url)
    return session.get(url, *args, **kwargs)


def patch(url, *args, **kwargs):
    session = get_session(url)
    return session.patch(url, *args, **kwargs)


def delete(url, *args, **kwargs):
    session = get_session(url)
    return session.delete(url, *args, **kwargs)


def head(url, *args, **kwargs):
    session = get_session(url)
    return session.head(url, *args, **kwargs)


def put(url, *args, **kwargs):
    session = get_session(url)
    return session.put(url, *args, **kwargs)


def options(url, *args, **kwargs):
    session = get_session(url)
    return session.options(url, *args, **kwargs)
