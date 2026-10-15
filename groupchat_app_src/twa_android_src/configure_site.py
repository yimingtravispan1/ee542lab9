"""Set the TWA URL and publish the matching public signing fingerprint.

HTTPS example: python configure_site.py --url https://YOUR_DOMAIN --sha256 FINGERPRINT
USB-only test: add --local-test and use http://localhost:8000.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True)
parser.add_argument('--sha256', required=True)
parser.add_argument('--local-test', action='store_true')
args = parser.parse_args()
site = urlsplit(args.url)
if site.username or site.password or site.query or site.fragment or site.path not in ('', '/'):
    parser.error('Use a root URL without credentials, query, or fragment.')
if not site.hostname or (site.scheme != 'https' and not (args.local_test and args.url.rstrip('/') == 'http://localhost:8000')):
    parser.error('HTTPS is required except for the explicit localhost USB test.')
fingerprint = args.sha256.upper()
if not re.fullmatch(r'(?:[0-9A-F]{2}:){31}[0-9A-F]{2}', fingerprint):
    parser.error('Expected a colon-separated SHA-256 certificate fingerprint.')
origin = f'{site.scheme}://{site.netloc}'
root = Path(__file__).resolve().parent
package = 'com.helloworld.groupchat.twa'
strings = ET.Element('resources')
ET.SubElement(strings, 'string', name='defaultUrl', translatable='false').text = origin + '/'
statements = [{'relation': ['delegate_permission/common.handle_all_urls'], 'target': {'namespace': 'web', 'site': origin}}]
ET.SubElement(strings, 'string', name='assetStatements', translatable='false').text = json.dumps(statements).replace('"', '\\"')
ET.indent(strings)
ET.ElementTree(strings).write(root / 'app/src/main/res/values/strings.xml', encoding='utf-8', xml_declaration=True)
assetlinks = [{'relation': ['delegate_permission/common.handle_all_urls'], 'target': {'namespace': 'android_app', 'package_name': package, 'sha256_cert_fingerprints': [fingerprint]}}]
(root.parent / 'frontend/.well-known/assetlinks.json').write_text(json.dumps(assetlinks, indent=2) + '\n', encoding='utf-8')
print('Configured TWA origin:', origin)
print('Package:', package)
print('Mode:', 'HTTPS TWA' if site.scheme == 'https' else 'USB local test; full TWA verification requires HTTPS')
