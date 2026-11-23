"""把 OpenAI / Claude 的 cookbook 類 repo 轉成繁中教材網站。

需要 GPU 的篇 -> notebooks/<來源>/<路徑>.ipynb（Colab 可直接跑）
其他篇       -> docs/<來源>/<路徑>.md（MkDocs 網站，程式碼用 code block 呈現）
各來源的原始 repo 要 clone 在旁邊（../openai-cookbook 等），見 SOURCES。

用法: python3 build.py      # 全部，並重產 mkdocs.yml 和首頁
已翻譯的檔案（notebook metadata / md frontmatter 有 translated: true）不會被覆蓋。
"""
import base64, glob, json, os, re, sys, yaml
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_REPO = 'ck10100713/agent-tutor'
GPU_RE = re.compile(r'^\s*(?:from|import)\s+(torch|transformers|vllm|unsloth|trl|peft)\b', re.M)
MAX_LINES = 40  # 網頁上每個 output 最多顯示幾行
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

# key 同時是輸出資料夾名稱；notice 會插在該來源每頁原文連結下方
SOURCES = {
    'openai': {'dir': 'openai-cookbook', 'repo': 'openai/openai-cookbook', 'branch': 'main',
               'key': 'OPENAI_API_KEY', 'name': 'OpenAI Cookbook'},
    'claude': {'dir': 'claude-cookbooks', 'repo': 'anthropics/claude-cookbooks', 'branch': 'main',
               'key': 'ANTHROPIC_API_KEY', 'name': 'Claude Cookbook'},
    'quickstarts': {'dir': 'claude-quickstarts', 'repo': 'anthropics/claude-quickstarts', 'branch': 'main',
                    'key': 'ANTHROPIC_API_KEY', 'name': 'Claude Quickstarts'},
    'prompt-tutorial': {'dir': 'prompt-eng-interactive-tutorial', 'repo': 'anthropics/prompt-eng-interactive-tutorial',
                        'branch': 'master', 'key': 'ANTHROPIC_API_KEY', 'name': 'Prompt 工程互動教學',
                        # 原 repo 沒有附授權，使用者決定公開並加註
                        'notice': '!!! note "個人閱讀用"\n    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。'
                                  '如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com'},
}

# ponytail: 下面這些是「目前處理中的來源」，use_source() 切換；一次只處理一個來源所以用全域變數
SRC = REPO = RAW = BRANCH = MD_OUT = NB_OUT = KEY = ''
PAGES = set()  # 目前來源中有 md 頁的篇（路徑不含副檔名）


def use_source(key):
    global SRC, REPO, RAW, BRANCH, MD_OUT, NB_OUT, KEY
    s = SOURCES[key]
    SRC = os.path.abspath(os.path.join(ROOT, '..', s['dir']))
    REPO = f"https://github.com/{s['repo']}"
    BRANCH = s['branch']
    RAW = f"https://raw.githubusercontent.com/{s['repo']}/{BRANCH}/"
    MD_OUT = os.path.join(ROOT, 'docs', key)
    NB_OUT = os.path.join(ROOT, 'notebooks', key)
    KEY = s['key']
    PAGES.clear()


def slug(stem):
    stem = stem.replace(' ', '_')  # 檔名有空白的（prompt 教學）網址不好看
    return re.sub(r'(^|/)\.', r'\1', stem)  # 點開頭的檔名 MkDocs 會當隱藏檔排除


def first_h1(text, fallback):
    m = re.search(r'(?m)^# (.+)', text)
    return m[1].strip() if m else fallback


def entries(key):
    """每個來源的篇目清單，統一成 {path, title, description, date, tags, archived}。"""
    if key in ('openai', 'claude'):
        reg = yaml.safe_load(open(os.path.join(SRC, 'registry.yaml')))
        for e in reg:
            e.setdefault('tags', e.get('categories'))  # claude 的 registry 叫 categories
        return reg
    if key == 'quickstarts':
        paths = ['README.md'] + sorted(os.path.relpath(p, SRC) for p in glob.glob(os.path.join(SRC, '*', 'README.md')))
        return [{'path': p, 'title': first_h1(open(os.path.join(SRC, p)).read(), p), 'tags': ['quickstarts']}
                for p in paths]
    if key == 'prompt-tutorial':
        out = []
        for p in sorted(glob.glob(os.path.join(SRC, 'Anthropic 1P', '*.ipynb'))):
            md = '\n'.join(''.join(c['source']) for c in json.load(open(p))['cells'] if c['cell_type'] == 'markdown')
            out.append({'path': os.path.relpath(p, SRC), 'title': first_h1(md, os.path.basename(p)), 'tags': ['prompt']})
        return out
    raise KeyError(key)


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
        return RAW + quote(path)
    text = re.sub(r'(!\[[^\]]*\]\()([^)\s]+)', lambda m: m[1] + resolve(m[2]), text)
    return re.sub(r'(<img[^>]*src=["\'])([^"\']+)', lambda m: m[1] + resolve(m[2]), text)


def setup_cell(cells, nb_dir, local_modules):
    code = '\n'.join(''.join(c['source']) for c in cells if c['cell_type'] == 'code')
    mods = set(re.findall(r'^\s*(?:from|import)\s+([A-Za-z_]\w*)', code, re.M))
    pkgs = sorted({PIP_NAME.get(m, m) for m in mods
                   if m not in sys.stdlib_module_names and m not in local_modules} - {None})
    lines = [f'# 環境設定：在 Colab 左側 🔑 Secrets 新增 {KEY}',
             f'%pip install -q -U {" ".join(pkgs or ["openai"])}',
             'import os',
             'try:',
             '    from google.colab import userdata',
             f"    os.environ['{KEY}'] = userdata.get('{KEY}')",
             'except ImportError:',
             '    pass  # 本機執行就用自己的環境變數']
    # ponytail: 有附資料檔/模組的才 sparse clone 該資料夾；examples/ 根目錄的共用資料在 examples/data
    sub = 'examples/data' if nb_dir == 'examples' else nb_dir
    if os.path.isdir(os.path.join(SRC, sub)) and os.listdir(os.path.join(SRC, sub)) != []:
        name = REPO.rsplit('/', 1)[1]
        lines += ['',
                  '# 抓原 repo 的資料檔（只下載這個資料夾）',
                  f"if not os.path.exists('{name}'):",
                  f'    !git clone -q --depth 1 --filter=blob:none --sparse {REPO}',
                  f"    !cd {name} && git sparse-checkout set '{sub}'",
                  f"os.chdir('{name}/{nb_dir}')"]
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
                     f"> 原文：[{path}]({REPO}/blob/{BRANCH}/{quote(path)})\n\n"
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
        page = os.path.join(MD_OUT, slug(os.path.splitext(target)[0]) + '.md')
        if os.path.splitext(target)[0] in PAGES:
            new = os.path.relpath(page, os.path.dirname(out))
        else:
            new = f'{REPO}/blob/{BRANCH}/{quote(target)}'
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
    stem = slug(os.path.splitext(entry['path'])[0])
    nb, cells = load_cells(entry)
    gpu = needs_gpu(cells)
    out = os.path.join(NB_OUT if gpu else MD_OUT, stem + ('.ipynb' if gpu else '.md'))
    if is_translated(out):
        return out, gpu
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if gpu:
        write_ipynb(entry, nb, cells, out)
    else:
        write_md(entry, cells, out)
    return out, gpu


# 側邊欄分類：registry tag -> 中文名稱，同一件事的 tag 併成一類
TAG_ZH = {
    'structured-outputs': 'Function calling', 'speech': '語音與音訊', 'transcription': '語音與音訊',
    'security': '安全防護與內容審查',
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
# OpenAI 的 tag 順序很隨意，這幾個幾乎每篇都掛，排在前面會把篇搶走，有更具體的 tag 就跳過
GENERIC_TAGS = {'completions', 'chat', 'tiktoken', 'embeddings'}
VECTOR_DB = '向量資料庫整合'


def openai_category(e):
    if e['path'].startswith('examples/vector_databases/'):
        return VECTOR_DB  # 各家向量資料庫的串接範例，跟 embedding 原理分開放
    tags = e.get('tags') or ['other']
    for t in tags:
        if t not in GENERIC_TAGS and t in TAG_ZH:
            return TAG_ZH[t]
    return TAG_ZH.get(tags[0], tags[0])


GPU_LABEL = '要 GPU 的篇（Colab）'
# 建議閱讀順序：首頁跟側邊欄共用這份
STAGES = [
    ('打基礎', ['Token 計算', '對話格式', '文字生成（Completions）', 'Responses API', 'Prompt 技巧']),
    ('讓模型用工具、會推理', ['Function calling', '推理模型', 'GPT-5 系列']),
    ('接上自己的資料', ['Embedding 與向量搜尋', VECTOR_DB, '知識圖譜']),
    ('做 Agent', ['Agent 開發', 'Agents SDK', 'MCP', 'Assistants API', 'Deep Research API']),
    ('上線前', ['評估（Evals）', '安全防護與內容審查', '微調（Fine-tuning）', '批次處理', '延遲優化', '用量 API']),
    ('多模態', ['語音與音訊', '即時語音（Realtime）', '影像理解（Vision）', '圖片生成', 'Sora 影片生成']),
    ('用 AI 寫程式', ['Codex', '軟體開發流程']),
    ('自己跑模型', ['開源模型（gpt-oss）', GPU_LABEL]),
    ('平台整合範例', ['ChatGPT 應用', 'GPT Actions 串接範例', '合作夥伴範例', '其他']),
]


# Claude Cookbook 的分類（registry categories 第一個）-> 中文，跟閱讀順序
CLAUDE_STAGES = [
    ('打基礎', [('Responses', 'Prompt 與回應技巧'), ('Thinking', 'Extended Thinking')]),
    ('工具與資料', [('Tools', '工具使用（Tool use）'), ('RAG & Retrieval', 'RAG 與檢索'), ('Multimodal', '多模態')]),
    ('做 Agent', [('Agent Patterns', 'Agent 設計模式'), ('Claude Agent SDK', 'Claude Agent SDK'),
                 ('Skills', 'Skills'), ('Claude Managed Agents', 'Claude Managed Agents')]),
    ('上線前', [('Evals', '評估（Evals）'), ('Observability', '監控與管理'), ('Fine-Tuning', '微調（Fine-tuning）')]),
    ('整合範例', [('Integrations', '第三方整合')]),
]


def notebook_title(path, fallback):
    first = ''.join(json.load(open(path))['cells'][0]['source'])
    line = first.splitlines()[0] if first else ''
    return line[2:] if line.startswith('# ') else fallback


def ordered(items):
    # 分類內也照建議順序：未封存的由舊到新（基礎的通常比較早寫），封存的放最後
    return sorted(items, key=lambda e: (bool(e.get('archived')), str(e.get('date'))))


def md_path(key, e):
    return f"{key}/{slug(os.path.splitext(e['path'])[0])}.md"


ARCHIVED = '原文已封存'


def mark_archived(page):
    """原 repo 標 archived 的篇：側邊欄顯示 deprecated 圖示、頁首顯示標籤。"""
    text = open(page).read()
    if '\nstatus: deprecated\n' in text:
        return
    # 插在 translated 那行後面，is_translated() 靠開頭判斷，不能動到
    open(page, 'w').write(re.sub(r'^(---\ntranslated: \w+\n)', rf'\1status: deprecated\ntags:\n- {ARCHIVED}\n', text, count=1))


def add_notice(page, notice):
    """在原文連結那行下面插入聲明；已經有就不重複插。"""
    text = open(page).read()
    if notice in text:
        return
    text = re.sub(r'(?m)^(> 原文：.*\n)', lambda m: m[1] + '\n' + notice + '\n', text, count=1)
    open(page, 'w').write(text)


def write_site(built):
    """built: {來源 key: (entries, gpu 的 path 集合)}"""
    nav: list = [{'首頁': 'index.md'}]
    home = ['# OpenAI & Claude 開發教材', '', '<div id="tutor-continue"></div>', '']  # 閱讀紀錄的「繼續閱讀」
    colab = f'https://colab.research.google.com/github/{SITE_REPO}/blob/main/notebooks/'

    def section(key, groups, stage_list):
        """groups: {分類名稱: [entries、現成的頁面路徑字串、或 (title, url)]}；stage_list: [(階段, [分類名稱])]"""
        order = [c for _, cats in stage_list for c in cats]
        extra = sorted(set(groups) - set(order))  # 還沒排進階段的新分類放最後
        if extra:
            print(f'[{key}] 還沒排進階段的分類：', extra)
            stage_list = stage_list + [('其他新分類', extra)]
        side = []
        home.extend([f"## {SOURCES[key]['name']}", ''])
        for n, (stage, cats) in enumerate(stage_list, 1):
            home.extend([f'### {n}. {stage}', ''])
            for label in cats:
                items = groups.get(label)
                if not items:
                    continue
                if isinstance(items[0], tuple):  # Colab 外部連結
                    side.append({label: [{t: u} for t, u in items]})
                    home.append(f'- {label}・{len(items)} 篇')
                    home.extend(f'    - [{t}]({u})' for t, u in items)
                else:
                    paths = [e if isinstance(e, str) else md_path(key, e) for e in items]
                    side.append({label: paths})
                    home.append(f'- [{label}]({paths[0]})・{len(items)} 篇')
            home.append('')
        nav.append({SOURCES[key]['name']: side})

    # OpenAI：依最具體的 tag 分類
    entries_, gpu_paths = built['openai']
    groups = {}
    for e in ordered(entries_):
        if e['path'] not in gpu_paths:
            groups.setdefault(openai_category(e), []).append(e)
    # 向量資料庫照廠商資料夾排，同一家放一起，總覽 README 第一
    groups.get(VECTOR_DB, []).sort(key=lambda e: (e['path'] != 'examples/vector_databases/README.md', e['path'].lower()))
    groups[GPU_LABEL] = [(notebook_title(os.path.join(ROOT, 'notebooks', 'openai', slug(os.path.splitext(e['path'])[0]) + '.ipynb'), e['title']),
                          colab + 'openai/' + slug(os.path.splitext(e['path'])[0]) + '.ipynb')
                         for e in ordered(entries_) if e['path'] in gpu_paths]
    groups[GPU_LABEL] = [(t + (f'（{ARCHIVED}）' if e.get('archived') else ''), u)
                         for (t, u), e in zip(groups[GPU_LABEL], [e for e in ordered(entries_) if e['path'] in gpu_paths])]
    section('openai', groups, STAGES)

    # Claude Cookbook
    entries_, gpu_paths = built['claude']
    zh = {en: z for _, cats in CLAUDE_STAGES for en, z in cats}
    groups = {}
    for e in ordered(entries_):
        if e['path'] in gpu_paths:
            continue  # ponytail: 目前 claude cookbook 沒有要 GPU 的篇，有的話再比照 OpenAI 加 Colab 分類
        cat = (e.get('tags') or ['other'])[0]
        groups.setdefault(zh.get(cat, cat), []).append(e)
    # prompt 教學照章節順序，放在 Claude 打基礎的第一個
    groups[SOURCES['prompt-tutorial']['name']] = [md_path('prompt-tutorial', e) for e in built['prompt-tutorial'][0]]
    stages = [(s, [z for _, z in cats]) for s, cats in CLAUDE_STAGES]
    stages[0][1].insert(0, SOURCES['prompt-tutorial']['name'])
    section('claude', groups, stages)

    # Quickstarts：照目錄順序，總覽放第一
    entries_, _ = built['quickstarts']
    nav.append({SOURCES['quickstarts']['name']: [md_path('quickstarts', e) for e in entries_]})
    home.extend([f"## {SOURCES['quickstarts']['name']}", '',
                 f"- [{len(entries_)} 個可部署的完整專案範本]({md_path('quickstarts', entries_[0])})", ''])

    open(os.path.join(ROOT, 'docs', 'index.md'), 'w').write('\n'.join(home))
    conf = {
        'site_name': 'OpenAI & Claude 開發教材',
        'site_url': f"https://{SITE_REPO.split('/')[0]}.github.io/{SITE_REPO.split('/')[1]}/",
        'repo_url': f'https://github.com/{SITE_REPO}',
        'docs_dir': 'docs',
        'use_directory_urls': False,
        'theme': {'name': 'material', 'language': 'zh-TW',
                  'features': ['content.code.copy', 'search.highlight', 'navigation.top', 'navigation.tabs',
                               'navigation.footer'],  # footer = 每頁底部的上一篇/下一篇
                  'palette': [{'media': '(prefers-color-scheme: light)', 'scheme': 'default',
                               'toggle': {'icon': 'material/weather-night', 'name': '深色模式'}},
                              {'media': '(prefers-color-scheme: dark)', 'scheme': 'slate',
                               'toggle': {'icon': 'material/weather-sunny', 'name': '淺色模式'}}]},
        'markdown_extensions': ['admonition', 'pymdownx.details', 'pymdownx.superfences', 'attr_list',
                                'md_in_html', 'tables', {'pymdownx.highlight': {'anchor_linenums': True}},
                                {'toc': {'permalink': True}}],
        'plugins': [{'search': {'lang': ['zh', 'en']}}, 'tags'],
        'extra': {'status': {'deprecated': ARCHIVED}},  # 側邊欄圖示的提示文字
        'extra_javascript': ['assets/progress.js'],  # 閱讀紀錄（localStorage）
        'extra_css': ['assets/progress.css'],
        'nav': nav,
    }
    yaml.safe_dump(conf, open(os.path.join(ROOT, 'mkdocs.yml'), 'w'), allow_unicode=True, sort_keys=False)


if __name__ == '__main__':
    built = {}
    for key in SOURCES:
        use_source(key)
        es = entries(key)
        PAGES.update(os.path.splitext(e['path'])[0] for e in es if not needs_gpu(load_cells(e)[1]))
        gpu_paths = set()
        for e in es:
            out, gpu = build(e)
            if gpu:
                gpu_paths.add(e['path'])
        built[key] = (es, gpu_paths)
        for e in es:
            page = os.path.join(MD_OUT, slug(os.path.splitext(e['path'])[0]) + '.md')
            if e.get('archived') and os.path.exists(page):
                mark_archived(page)
        if SOURCES[key].get('notice'):
            for e in es:
                add_notice(os.path.join(MD_OUT, slug(os.path.splitext(e['path'])[0]) + '.md'), SOURCES[key]['notice'])
        print(f'{key}: {len(es)} 篇，GPU {len(gpu_paths)} 篇')
    write_site(built)
