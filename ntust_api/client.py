import requests
from urllib.parse import urlparse

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

class NtustClient:
    def __init__(self, user_agent=DEFAULT_USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def get(self, url, **kwargs):
        resp = self.session.get(url, **kwargs)
        resp.encoding = 'utf-8' # Force utf-8 for NTUST API
        return resp

    def post(self, url, **kwargs):
        resp = self.session.post(url, **kwargs)
        resp.encoding = 'utf-8' # Force utf-8 for NTUST API
        return resp

    def set_cookie(self, name, value, domain):
        cookie_obj = requests.cookies.create_cookie(name=name, value=value, domain=domain)
        self.session.cookies.set_cookie(cookie_obj)

    def clear_cookies(self):
        self.session.cookies.clear()
