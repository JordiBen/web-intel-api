"""Download Wappalyzer-format fingerprints from the HTTP Archive fork (GPL-3.0) into data/.
Pinned to a commit for reproducible builds. Run: python3 data/update_fingerprints.py [commit-sha]"""
import json, pathlib, string, sys, urllib.request

REPO = 'HTTPArchive/wappalyzer'
HERE = pathlib.Path(__file__).parent


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main():
    sha = sys.argv[1] if len(sys.argv) > 1 else json.loads(get(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    base = f'https://raw.githubusercontent.com/{REPO}/{sha}/src'
    techs = {}
    for ch in '_' + string.ascii_lowercase:
        techs.update(json.loads(get(f'{base}/technologies/{ch}.json')))
    cats = json.loads(get(f'{base}/categories.json'))
    (HERE / 'technologies.json').write_text(json.dumps(techs, separators=(',', ':'), ensure_ascii=False))
    (HERE / 'categories.json').write_text(json.dumps(cats, separators=(',', ':'), ensure_ascii=False))
    (HERE / 'SOURCE.txt').write_text(f'Fingerprints from https://github.com/{REPO} at commit {sha}\n'
                                     'Licensed under GPL-3.0 (see LICENSE). Original project: Wappalyzer.\n')
    print(len(techs), 'technologies,', len(cats), 'categories @', sha[:10])


if __name__ == '__main__':
    main()
