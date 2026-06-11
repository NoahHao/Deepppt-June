#!/usr/bin/env python3
"""
网页PPT爬虫 v3.0 — 先搜索过滤 + 递归遍历 + JS渲染SPA
======================================================
用法：
  python web_ppt_crawler.py --query "AI 安全"       # 按关键词过滤下载
  python web_ppt_crawler.py --scan                   # 全量下载
  python web_ppt_crawler.py --query "存储" --js       # 启用JS渲染(SPA)
  python web_ppt_crawler.py --query "存储" --recall 3
"""

import sys, os, json, re, urllib.request, urllib.parse, ssl, subprocess, tempfile
from pathlib import Path
from html.parser import HTMLParser

SKILL_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = SKILL_ROOT / "output" / "web_ppts"


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.base = ""
    def handle_starttag(self, tag, attrs):
        if tag == "base":
            for k, v in attrs:
                if k == "href": self.base = v
        if tag == "a":
            for k, v in attrs:
                if k == "href": self.links.append(v)


# ════════════════════════════════════════════════════════════
# JS渲染支持
# ════════════════════════════════════════════════════════════

def _detect_spa(html):
    """检测是否为SPA页面"""
    hints = ['react', 'vue', 'angular', 'ng-app', '__nuxt', '__next',
             'data-reactroot', 'v-bind', 'ng-version', 'id="app"', 'id="root"',
             'class="app', 'webpack', 'chunk-', 'loading', 'skeleton', 'spinner']
    return any(h in html.lower() for h in hints)


def fetch_rendered_html(url, timeout=30):
    """
    获取JS渲染后的HTML。按优先级：Edge headless > Chrome headless
    """
    # Method 1: Edge headless
    edge_paths = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]
    for p in edge_paths:
        if os.path.exists(p):
            try:
                r = subprocess.run(
                    [p, '--headless', '--disable-gpu', '--dump-dom', '--no-sandbox', url],
                    capture_output=True, timeout=timeout, shell=False
                )
                if r.returncode == 0 and len(r.stdout) > 500:
                    return r.stdout.decode('utf-8', errors='replace')
            except: pass

    # Method 2: Chrome headless
    chrome_paths = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for p in chrome_paths:
        if os.path.exists(p):
            try:
                r = subprocess.run(
                    [p, '--headless', '--disable-gpu', '--dump-dom', '--no-sandbox', url],
                    capture_output=True, timeout=timeout, shell=False
                )
                if r.returncode == 0 and len(r.stdout) > 500:
                    return r.stdout.decode('utf-8', errors='replace')
            except: pass

    return None


# ════════════════════════════════════════════════════════════
# 爬取与下载
# ════════════════════════════════════════════════════════════

def load_website_config():
    config_file = SKILL_ROOT / "config" / "websites.json"
    if not config_file.exists(): return []
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return [s for s in config.get("sources", []) if s.get("enabled", False)]


def crawl_website(url, keywords=None, recursive=True, max_depth=2, use_js=False):
    """
    爬取网站寻找PPTX/PPT链接。支持递归子目录 + JS渲染SPA。
    """
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    ppt_links = set()
    subdir_links = set()
    final_url = url
    html = None
    file_exts = {'.pptx', '.ppt', '.pdf', '.docx', '.doc', '.xlsx', '.png', '.jpg',
                 '.jpeg', '.gif', '.mp4', '.zip', '.html', '.htm', '.js', '.css'}
    
    # Fetch HTML
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            final_url = resp.geturl()
    except:
        use_js = True

    # SPA detection
    if use_js and html is None:
        print("    [js] urllib failed, trying headless browser...")
    elif use_js or (html and _detect_spa(html)):
        if use_js: print("    [js] JS rendering mode...")

    # Parse links from HTML
    def parse_links(parsed_html, label=""):
        nonlocal final_url
        p = LinkExtractor()
        p.feed(parsed_html)
        found = 0
        for link in p.links:
            if not link or link.startswith('#') or link.startswith('javascript:'):
                continue
            full_url = urllib.parse.urljoin(final_url, link)
            link_lower = link.lower()
            if link_lower.endswith('.pptx') or link_lower.endswith('.ppt'):
                if keywords:
                    url_text = urllib.parse.unquote(full_url).lower()
                    if any(kw.lower() in url_text for kw in keywords):
                        ppt_links.add(full_url); found += 1
                else:
                    ppt_links.add(full_url); found += 1
            elif recursive:
                has_known_ext = any(link_lower.endswith(ext) for ext in file_exts)
                if not has_known_ext or link_lower.endswith('/'):
                    if full_url.startswith(final_url.rstrip('/')):
                        subdir_links.add(full_url)
        return found

    if html:
        parse_links(html)

    # JS rendering for SPA
    if not ppt_links and (use_js or (html and _detect_spa(html))):
        rendered = fetch_rendered_html(url)
        if rendered:
            js_found = parse_links(rendered, "[js]")
            print(f"    [js] Rendered: {js_found} PPT links found")
        elif use_js:
            print("    [warn] No browser available (Edge/Chrome not found)")

    # Recursive crawl
    if recursive and max_depth > 1 and subdir_links:
        print(f"    [recursive] {len(subdir_links)} subdirs...")
        for sub_url in sorted(subdir_links)[:20]:
            sub_ppts = crawl_website(sub_url, keywords=keywords, recursive=False, max_depth=0, use_js=use_js)
            ppt_links.update(sub_ppts)

    return list(ppt_links)


def download_ppt(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    filename = urllib.parse.urlparse(url).path.split('/')[-1]
    if not filename.endswith(('.pptx', '.ppt')): filename += '.pptx'
    filepath = os.path.join(output_dir, filename)
    if os.path.exists(filepath):
        print(f"    [skip] {filename}"); return filepath
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False; ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
            with open(filepath, 'wb') as f: f.write(resp.read())
        print(f"    [ok] {filename} ({os.path.getsize(filepath)/1024:.0f}KB)")
        return filepath
    except Exception as e:
        print(f"    [fail] {filename} - {e}")
        return None


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════

def crawl_and_search(query, recall_n=0, use_js=False):
    sources = load_website_config()
    if not sources:
        print("未配置网站源。请在 config/websites.json 中添加 sources。")
        return []
    keywords = re.split(r'[\s,，、]+', query) if query else None
    downloaded = []
    for src in sources:
        print(f"Searching {src['name']}: {src['url']}")
        links = crawl_website(src['url'], keywords=keywords, use_js=use_js)
        if not keywords:
            print(f"  Full mode: {len(links)} PPTs")
        else:
            print(f"  Keywords [{', '.join(keywords)}]: {len(links)} PPTs matched")
        for link in links:
            path = download_ppt(link, DOWNLOAD_DIR)
            if path: downloaded.append(path)
        print()
    if downloaded:
        print(f"Downloaded: {len(downloaded)} files. Updating index...")
        try:
            sys.path.insert(0, str(SKILL_ROOT))
            from scripts.kb_search import KBEngine
            kb = KBEngine(); kb.scan()
            if recall_n and query:
                results = kb.search(query, top_k=recall_n)
                if results:
                    for i in range(min(recall_n, len(results))):
                        r = kb.recall(results[i][0])
                        if r: print(f"  Recalled: {r['output']}")
            print(f"KB: {len(kb.index)} files")
        except Exception as e: print(f"  [warn] {e}")
    return downloaded


if __name__ == "__main__":
    query = ""; recall_n = 0; use_js = False
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        query = sys.argv[idx+1] if len(sys.argv) > idx+1 else ""
    if "--recall" in sys.argv:
        idx = sys.argv.index("--recall")
        recall_n = int(sys.argv[idx+1]) if len(sys.argv) > idx+1 else 0
    if "--js" in sys.argv: use_js = True
    if "--scan" in sys.argv or "--query" in sys.argv:
        crawl_and_search(query, recall_n, use_js)
    else:
        print("Usage:")
        print("  python web_ppt_crawler.py --query 'AI 安全'        # keyword filter")
        print("  python web_ppt_crawler.py --query '存储' --js      # SPA + JS render")
        print("  python web_ppt_crawler.py --query '存储' --recall 3")
        print("  python web_ppt_crawler.py --scan                   # full download")
