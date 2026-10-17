import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault('RAPIDAPI_PROXY_SECRET', 'test-proxy-secret')
os.environ.setdefault('API_KEYS', 'k1,k2')
os.environ.setdefault('X402_PAY_TO', '0x000000000000000000000000000000000000dEaD')
os.environ.setdefault('X402_NETWORK', 'eip155:84532')
os.environ.setdefault('PUBLIC_BASE_URL', 'https://api.example.test')
os.environ.setdefault('ZYLA_SECRET', 'test-zyla-secret')
os.environ.setdefault('APIMARKET_SECRET', 'test-apimarket-secret')
