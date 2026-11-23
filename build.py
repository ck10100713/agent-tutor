"""把 openai-cookbook 轉成教材。

需要 GPU 的篇 -> notebooks/<路徑>.ipynb（Colab 可直接跑）
其他篇       -> docs/<路徑>.md（MkDocs 網站，程式碼用 code block 呈現）

用法: python3 build.py            # 全部，並重產 mkdocs.yml
      python3 build.py <path>...  # 只做指定的 registry path
已翻譯的檔案（notebook metadata / md frontmatter 有 translated: true）不會被覆蓋。
"""
import base64, json, os, re, sys, yaml

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openai-cookbook'))
ROOT = os.path.dirname(os.path.abspath(__file__))
NB_OUT = os.path.join(ROOT, 'notebooks')
MD_OUT = os.path.join(ROOT, 'docs')
PAGES = set()  # 有 md 頁的篇（路徑不含副檔名），main 會填
GPU_RE = re.compile(r'^\s*(?:from|import)\s+(torch|transformers|vllm|unsloth|trl|peft)\b', re.M)
MAX_LINES = 40  # 網頁上每個 output 最多顯示幾行
SITE_REPO = 'ck10100713/agent-tutor'
RAW = 'https://raw.githubusercontent.com/openai/openai-cookbook/main/'
REPO = 'https://github.com/openai/openai-cookbook'
MAX_OUTPUT = 50_000  # ponytail: 單一 cell output 超過 50KB 就丟掉，Colab 重跑就有

# import 名稱 -> pip 套件名，只列名字對不上的；其他直接用 import 名
PIP_NAME = {'sklearn': 'scikit-learn', 'PIL': 'pillow', 'cv2': 'opencv-python', 'yaml': 'pyyaml',
            'dotenv': 'python-dotenv', 'bs4': 'beautifulsoup4', 'docx': 'python-docx',
            'fitz': 'pymupdf', 'agents': 'openai-agents', 'google': None, 'IPython': None,
            'faiss': 'faiss-cpu',
            # PyPI 上同名的是不相干的套件，要裝官方 git 版本
            'clip': 'git+https://github.com/openai/CLIP.git',
            'segment_anything': 'git+https://github.com/facebookresearch/segment-anything.git'}
# ponytail: 套件名是從 import 推出來的，新增 GPU 篇時要人工看一下 setup cell 的 pip install 行


def md_cell(text):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': text}


def code_cell(text):
    return {'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': text}


def md_to_cells(text):
    """.md/.mdx 文章：```python 區塊變 code cell，其他依 ## 標題切成 markdown cell。"""
    cells = []
    for i, part in enumerate(re.split(r'^```(?:python|py)\s*\n(.*?)^```\s*$', text, flags=re.S | re.M)):
        if i % 2:
            cells.append(code_cell(part.rstrip()))
        else:
            for sec in re.split(r'(?m)^(?=## )', part):
                if sec.strip():
                    cells.append(md_cell(sec.strip()))
    return cells


def fix_links(text, nb_dir):
    """相對路徑的圖片/連結改成 GitHub raw 網址，Colab 裡才看得到。"""
    def resolve(url):
        if re.match(r'^(https?:|data:|attachment:|#|mailto:)', url):
            return url
        path = url.lstrip('/') if url.startswith('/') else os.path.normpath(os.path.join(nb_dir, url))
        return RAW + path
    text = re.sub(r'(!\[[^\]]*\]\()([^)\s]+)', lambda m: m[1] + resolve(m[2]), text)
    return re.sub(r'(<img[^>]*src=["\'])([^"\']+)', lambda m: m[1] + resolve(m[2]), text)


def setup_cell(cells, nb_dir, local_modules):
    code = '\n'.join(''.join(c['source']) for c in cells if c['cell_type'] == 'code')
    mods = set(re.findall(r'^\s*(?:from|import)\s+([A-Za-z_]\w*)', code, re.M))
    pkgs = sorted({PIP_NAME.get(m, m) for m in mods
                   if m not in sys.stdlib_module_names and m not in local_modules} - {None})
    lines = ['# 環境設定：在 Colab 左側 🔑 Secrets 新增 OPENAI_API_KEY',
             f'%pip install -q -U {" ".join(pkgs or ["openai"])}',
             'import os',
             'try:',
             '    from google.colab import userdata',
             "    os.environ['OPENAI_API_KEY'] = userdata.get('OPENAI_API_KEY')",
             'except ImportError:',
             '    pass  # 本機執行就用自己的環境變數']
    # ponytail: 有附資料檔/模組的才 sparse clone 該資料夾；examples/ 根目錄的共用資料在 examples/data
    sub = 'examples/data' if nb_dir == 'examples' else nb_dir
    if os.path.isdir(os.path.join(SRC, sub)) and os.listdir(os.path.join(SRC, sub)) != []:
        lines += ['',
                  '# 抓原 repo 的資料檔（只下載這個資料夾）',
                  "if not os.path.exists('openai-cookbook'):",
                  f'    !git clone -q --depth 1 --filter=blob:none --sparse {REPO}',
                  f'    !cd openai-cookbook && git sparse-checkout set {sub}',
                  f"os.chdir('openai-cookbook/{nb_dir}')"]
    return code_cell('\n'.join(lines))


def is_translated(out):
    if not os.path.exists(out):
        return False
    if out.endswith('.ipynb'):
        return json.load(open(out))['metadata'].get('tutor', {}).get('translated', False)
    return open(out).read(300).startswith('---\ntranslated: true')


def load_cells(entry):
    """回傳 Colab 版完整 cell 列表：[header, setup, *內文, footer]。"""
    path = entry['path']
    nb_dir = os.path.dirname(path)
    src = os.path.join(SRC, path)
    if path.endswith('.ipynb'):
        nb = json.load(open(src))
        cells = nb['cells']
    else:
        nb = {}
        cells = md_to_cells(open(src).read())

    for c in cells:
        c['source'] = ''.join(c['source']) if isinstance(c['source'], list) else c['source']
        if c['cell_type'] == 'markdown':
            c['source'] = fix_links(c['source'], nb_dir)
        elif c['cell_type'] == 'code':
            c['outputs'] = [o for o in c.get('outputs', []) if len(json.dumps(o)) < MAX_OUTPUT]

    local = {os.path.splitext(f)[0] for f in os.listdir(os.path.join(SRC, nb_dir))} | {'openai_cookbook'}
    header = md_cell(f"# {entry['title']}\n\n"
                     f"> 原文：[{path}]({REPO}/blob/main/{path})\n\n"
                     f"{entry.get('description', '')}\n\n"
                     "<!-- tutor:goals -->")
    footer = md_cell('<!-- tutor:summary -->')
    return nb, [header, setup_cell(cells, nb_dir, local), *cells, footer]


def write_ipynb(entry, nb, cells, out):
    nb['cells'] = cells
    nb['metadata'] = {'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
                      'colab': {'provenance': []}, 'tutor': {'source': entry['path'], 'tags': entry.get('tags', [])}}
    nb.setdefault('nbformat', 4); nb.setdefault('nbformat_minor', 5)
    json.dump(nb, open(out, 'w'), ensure_ascii=False, indent=1)


def fence(code, lang=''):
    ticks = '`' * max(3, max((len(m) for m in re.findall(r'`+', code)), default=0) + 1)
    return f'{ticks}{lang}\n{code.rstrip()}\n{ticks}'


def outputs_md(outputs, files_dir, n):
    parts = []
    for k, o in enumerate(outputs):
        data = o.get('data', {})
        if o['output_type'] == 'stream':
            text = ''.join(o['text'])
        elif o['output_type'] == 'error':
            text = f"{o['ename']}: {o['evalue']}"
        elif 'image/png' in data:
            name = f'out_{n}_{k}.png'
            os.makedirs(files_dir, exist_ok=True)
            open(os.path.join(files_dir, name), 'wb').write(base64.b64decode(''.join(data['image/png'])))
            parts.append(f'![]({os.path.basename(files_dir)}/{name})')
            continue
        elif 'text/plain' in data:
            text = ''.join(data['text/plain'])
        else:
            continue  # ponytail: 只有 html/widget 的 output 直接略過
        lines = re.sub(r'\x1b\[[0-9;]*m', '', text).rstrip().splitlines()
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f'... (省略 {len(lines) - MAX_LINES} 行)']
        if lines:
            parts.append(fence('\n'.join(lines), 'text'))
    if not parts:
        return ''
    body = '\n\n'.join(parts)
    return '??? note "輸出"\n\n' + '\n'.join('    ' + l if l else '' for l in body.splitlines())


def fix_page_links(text, nb_dir, out):
    """非圖片的相對連結：有教材頁就連 .md，沒有就連 GitHub 原檔。"""
    def resolve(m):
        url, anchor = (m[2].split('#', 1) + [''])[:2]
        if not url or re.match(r'^[a-z]+:', url):
            return m[0]
        target = url.lstrip('/') if url.startswith('/') else os.path.normpath(os.path.join(nb_dir, url))
        page = os.path.join(MD_OUT, os.path.splitext(target)[0] + '.md')
        if os.path.splitext(target)[0] in PAGES:
            new = os.path.relpath(page, os.path.dirname(out))
        else:
            new = f'{REPO}/blob/main/{target}'
        return m[1] + new + (f'#{anchor}' if anchor else '')
    return re.sub(r'((?<!!)\[[^\]]*\]\()([^)\s]+)', resolve, text)


def write_md(entry, cells, out, translated=False):
    files_dir = out[:-3] + '_files'
    parts = [f"---\ntranslated: {str(translated).lower()}\nsource: {entry['path']}\n---"]
    seen_h1 = False
    for n, c in enumerate(cells):
        if n == 1:
            continue  # setup cell 是給 Colab 用的
        if c['cell_type'] == 'markdown':
            text = c['source']
            if n > 1 and not seen_h1 and re.search(r'(?m)^# ', text):
                text = re.sub(r'(?m)^# .*\n?', '', text, count=1)  # 原文 H1 跟開頭標題重複
                seen_h1 = True
            for name, mime in (c.get('attachments') or {}).items():
                if name != os.path.basename(name) or name.startswith('.'):
                    continue  # 附件檔名不可以帶路徑
                os.makedirs(files_dir, exist_ok=True)
                open(os.path.join(files_dir, name), 'wb').write(base64.b64decode(''.join(next(iter(mime.values())))))
                text = text.replace(f'attachment:{name}', f'{os.path.basename(files_dir)}/{name}')
            parts.append(fix_page_links(text, os.path.dirname(entry['path']), out))
        elif c['cell_type'] == 'code' and c['source'].strip():
            parts.append(fence(c['source'], 'python'))
            out_md = outputs_md(c.get('outputs', []), files_dir, n)
            if out_md:
                parts.append(out_md)
    open(out, 'w').write('\n\n'.join(parts) + '\n')


def needs_gpu(cells):
    return bool(GPU_RE.search('\n'.join(c['source'] for c in cells if c['cell_type'] == 'code')))


def build(entry):
    stem = os.path.splitext(entry['path'])[0]
    nb, cells = load_cells(entry)
    gpu = needs_gpu(cells)
    out = os.path.join(NB_OUT if gpu else MD_OUT, stem + ('.ipynb' if gpu else '.md'))
    if is_translated(out):
        return out, gpu
    # 之前翻好的 notebook 要轉成 md 時，沿用它的翻譯內容
    old_nb = os.path.join(NB_OUT, stem + '.ipynb')
    reuse = not gpu and is_translated(old_nb)
    if reuse:
        cells = json.load(open(old_nb))['cells']
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if gpu:
        write_ipynb(entry, nb, cells, out)
    else:
        write_md(entry, cells, out, translated=reuse)
    return out, gpu


# 側邊欄分類：registry 第一個 tag -> 中文名稱，同一件事的 tag 併成一類
TAG_ZH = {
    'embeddings': 'Embedding 與向量搜尋', 'completions': '文字生成（Completions）',
    'gpt-actions-library': 'GPT Actions 串接範例', 'agents-sdk': 'Agents SDK',
    'agents': 'Agent 開發', 'agents-api': 'Agent 開發', 'agentkit': 'Agent 開發',
    'evals': '評估（Evals）', 'evals-api': '評估（Evals）', 'responses': 'Responses API', 'codex': 'Codex',
    'audio': '語音與音訊', 'whisper': '語音與音訊',
    'realtime': '即時語音（Realtime）', 'realtime-api': '即時語音（Realtime）', 'gpt-realtime-mini': '即時語音（Realtime）',
    'partners': '合作夥伴範例', 'chatgpt': 'ChatGPT 應用',
    'images': '圖片生成', 'image-generation': '圖片生成', 'dall-e': '圖片生成', 'vision': '影像理解（Vision）',
    'gpt-5': 'GPT-5 系列', 'gpt-5.1': 'GPT-5 系列', 'gpt-5.2': 'GPT-5 系列',
    'gpt-oss': '開源模型（gpt-oss）', 'open-models': '開源模型（gpt-oss）', 'mcp': 'MCP',
    'tiktoken': 'Token 計算', 'guardrails': '安全防護與內容審查', 'moderation': '安全防護與內容審查',
    'prompt': 'Prompt 技巧', 'prompt-caching': 'Prompt 技巧',
    'fine-tuning': '微調（Fine-tuning）', 'reinforcement-learning': '微調（Fine-tuning）',
    'assistants': 'Assistants API', 'chat': '對話格式', 'deep-research-api': 'Deep Research API',
    'sora': 'Sora 影片生成', 'knowledge-graphs': '知識圖譜', 'functions': 'Function calling',
    'batch': '批次處理', 'latency': '延遲優化', 'SDLC': '軟體開發流程', 'usage-api': '用量 API',
    'reasoning': '推理模型', 'other': '其他',
}


def write_site(registry, gpu_paths):
    by_tag = {}
    for e in registry:
        if e['path'] not in gpu_paths:
            tag = (e.get('tags') or ['other'])[0]
            by_tag.setdefault(TAG_ZH.get(tag, tag), []).append(e)  # 沒對照到的就用原 tag
    nav: list = [{'首頁': 'index.md'}]
    for tag in sorted(by_tag, key=lambda t: -len(by_tag[t])):
        items = sorted(by_tag[tag], key=lambda e: str(e.get('date')), reverse=True)
        # 不寫標題，讓 MkDocs 用頁面的 H1，翻譯後側邊欄就會是中文
        nav.append({tag: [os.path.splitext(e['path'])[0] + '.md' for e in items]})
    conf = {
        'site_name': 'OpenAI Cookbook 繁中教材',
        'site_url': f"https://{SITE_REPO.split('/')[0]}.github.io/{SITE_REPO.split('/')[1]}/",
        'repo_url': f'https://github.com/{SITE_REPO}',
        'docs_dir': 'docs',
        'use_directory_urls': False,
        'theme': {'name': 'material', 'language': 'zh-TW',
                  'features': ['content.code.copy', 'search.highlight', 'navigation.top'],
                  'palette': [{'media': '(prefers-color-scheme: light)', 'scheme': 'default',
                               'toggle': {'icon': 'material/weather-night', 'name': '深色模式'}},
                              {'media': '(prefers-color-scheme: dark)', 'scheme': 'slate',
                               'toggle': {'icon': 'material/weather-sunny', 'name': '淺色模式'}}]},
        'markdown_extensions': ['admonition', 'pymdownx.details', 'pymdownx.superfences', 'attr_list',
                                'md_in_html', 'tables', {'pymdownx.highlight': {'anchor_linenums': True}},
                                {'toc': {'permalink': True}}],
        'plugins': [{'search': {'lang': ['zh', 'en']}}],
        'nav': nav,
    }
    yaml.safe_dump(conf, open(os.path.join(ROOT, 'mkdocs.yml'), 'w'), allow_unicode=True, sort_keys=False)

    gpu = [e for e in registry if e['path'] in gpu_paths]
    lines = ['# OpenAI Cookbook 繁中教材', '',
             f'左邊依主題分類，共 {sum(len(v) for v in by_tag.values())} 篇。', '',
             '## 要 GPU 的篇（用 Colab 跑）', '']
    colab = f'https://colab.research.google.com/github/{SITE_REPO}/blob/main/notebooks/'
    for e in gpu:  # 標題用翻好的 notebook 第一行
        stem = os.path.splitext(e['path'])[0]
        first = json.load(open(os.path.join(NB_OUT, stem + '.ipynb')))['cells'][0]['source']
        title = ''.join(first).splitlines()[0].lstrip('# ') or e['title']
        lines.append(f'- [{title}]({colab}{stem}.ipynb)')
    open(os.path.join(MD_OUT, 'index.md'), 'w').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    registry = yaml.safe_load(open(os.path.join(SRC, 'registry.yaml')))
    PAGES.update(os.path.splitext(e['path'])[0] for e in registry if not needs_gpu(load_cells(e)[1]))
    wanted = set(sys.argv[1:])
    gpu_paths = set()
    for e in registry:
        if not wanted or e['path'] in wanted:
            out, gpu = build(e)
            if gpu:
                gpu_paths.add(e['path'])
            print(out)
    if not wanted:
        write_site(registry, gpu_paths)
