"""翻譯前後處理。agent 只碰文字，程式碼/輸出/內嵌圖片都換成佔位符。

python3 i18n.py split          # docs 裡 translated: false 的頁 -> work/<id>/src.N.md，並產生 work/batches.json
python3 i18n.py split-nb       # notebooks 裡還沒翻的 -> work/<id>/，印出 id 清單（不動 batches.json）
python3 i18n.py merge <id>     # work/<id>/zh.N.md 組回 docs，檢查不過就印錯誤、exit 1
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, 'docs')
WORK = os.path.join(ROOT, 'work')
PART_CHARS = 12_000   # 每個 part 的上限，讓 agent 一次寫得完
BATCH_CHARS = 60_000  # 每個 agent 分到的文字量
FENCE = re.compile(r'^(\s*)(`{3,}|~{3,})')
MARK = re.compile(r'⟦[KDM]\d+⟧')  # M = notebook 的 markdown cell 開頭


def page_id(rel):
    return rel[:-3].replace('/', '__')


def split_body(body):
    """回傳 (含佔位符的文字, 佔位符 -> 原文)。"""
    keep, out, lines, i = {}, [], body.split('\n'), 0
    while i < len(lines):
        line = lines[i]
        m = FENCE.match(line)
        if m:
            j = i + 1
            while j < len(lines) and lines[j].strip() != m[2]:
                j += 1
            key = f'⟦K{len(keep)}⟧'
            keep[key] = '\n'.join([line[len(m[1]):]] + lines[i + 1:j + 1])  # 縮排留在佔位符那行
            out.append(m[1] + key)
            i = j + 1
            continue
        if line.startswith('??? note "輸出"'):
            j = i + 1
            while j < len(lines) and (lines[j].startswith('    ') or not lines[j].strip()):
                j += 1
            while not lines[j - 1].strip():  # 尾巴的空行還給內文
                j -= 1
            key = f'⟦K{len(keep)}⟧'
            keep[key] = '\n'.join(lines[i:j])
            out.append(key)
            i = j
            continue
        out.append(line)
        i += 1

    def data_uri(m):
        key = f'⟦D{len(keep)}⟧'
        keep[key] = m[0]
        return key
    return re.sub(r'data:[a-z]+/[^)"\'\s]+', data_uri, '\n'.join(out)), keep


def split_notebooks():
    """notebook：code cell 變 ⟦K⟧，每個 markdown cell 前面放 ⟦M⟧ 標記邊界。"""
    nb_root = os.path.join(ROOT, 'notebooks')
    for root, _, files in os.walk(nb_root):
        for f in files:
            path = os.path.join(root, f)
            nb = json.load(open(path))
            if not f.endswith('.ipynb') or nb['metadata'].get('tutor', {}).get('translated'):
                continue
            keep, blocks = {}, []
            for i, c in enumerate(nb['cells']):
                if c['cell_type'] != 'markdown':
                    blocks.append(f'⟦K{i}⟧')
                    continue
                def data_uri(m):
                    key = f'⟦D{len(keep)}⟧'
                    keep[key] = m[0]
                    return key
                blocks.append(f'⟦M{i}⟧\n' + re.sub(r'data:[a-z]+/[^)"\'\s]+', data_uri, ''.join(c['source'])))
            pid = 'nb__' + os.path.relpath(path, nb_root)[:-6].replace('/', '__')
            d = os.path.join(WORK, pid)
            os.makedirs(d, exist_ok=True)
            parts = split_parts('\n\n'.join(blocks) + '\n')
            for n, p in enumerate(parts, 1):
                open(os.path.join(d, f'src.{n}.md'), 'w').write(p)
            json.dump({'doc': os.path.relpath(path, ROOT), 'kind': 'ipynb', 'parts': len(parts), 'keep': keep},
                      open(os.path.join(d, 'meta.json'), 'w'), ensure_ascii=False)
            print(pid)


def merge_notebook(meta, zh):
    path = os.path.join(ROOT, meta['doc'])
    nb = json.load(open(path))
    pieces = re.split(r'(⟦[MK]\d+⟧)', zh)
    for k, tok in enumerate(pieces):
        if tok.startswith('⟦M'):
            text = pieces[k + 1]
            text = text[1:] if text.startswith('\n') else text  # 拿掉 split 時加的換行，cell 原本的空行保留
            text = text[:-2] if text.endswith('\n\n') else text.rstrip('\n')
            nb['cells'][int(tok[2:-1])]['source'] = re.sub(r'⟦D\d+⟧', lambda m: meta['keep'][m[0]], text)
    nb['metadata'].setdefault('tutor', {})['translated'] = True
    json.dump(nb, open(path, 'w'), ensure_ascii=False, indent=1)


def split_parts(text):
    paras = re.split(r'(?<=\n)\n', text)  # 在空行切，不切斷段落
    paras = [p + '\n' for p in paras[:-1]] + paras[-1:]  # 把切掉的換行補回去
    parts, cur = [], ''
    for para in paras:
        if cur and len(cur) + len(para) > PART_CHARS:
            parts.append(cur)
            cur = ''
        cur += para
    return parts + [cur]


def split_all():
    pages = []
    for root, _, files in os.walk(DOCS):
        for f in files:
            path = os.path.join(root, f)
            if not f.endswith('.md') or f == 'index.md':
                continue
            raw = open(path).read()
            if not raw.startswith('---\ntranslated: false'):
                continue
            front, body = raw.split('\n---\n', 1)
            text, keep = split_body(body)
            pid = page_id(os.path.relpath(path, DOCS))
            d = os.path.join(WORK, pid)
            os.makedirs(d, exist_ok=True)
            parts = split_parts(text)
            for n, p in enumerate(parts, 1):
                open(os.path.join(d, f'src.{n}.md'), 'w').write(p)
            json.dump({'doc': os.path.relpath(path, ROOT), 'front': front, 'parts': len(parts), 'keep': keep},
                      open(os.path.join(d, 'meta.json'), 'w'), ensure_ascii=False)
            pages.append((pid, len(text)))
    # 大的先排，各批大小比較平均
    batches, sizes = [], []
    for pid, n in sorted(pages, key=lambda x: -x[1]):
        k = next((k for k, s in enumerate(sizes) if s + n <= BATCH_CHARS), None)
        if k is None:
            batches.append([]); sizes.append(0); k = len(batches) - 1
        batches[k].append(pid); sizes[k] += n
    json.dump(batches, open(os.path.join(WORK, 'batches.json'), 'w'), indent=1)
    print(f'{len(pages)} 頁，{sum(n for _, n in pages):,} 字元，{len(batches)} 批')


def check(src, zh):
    errs = []
    if MARK.findall(src) != MARK.findall(zh):
        errs.append(f'佔位符不一致：原文 {MARK.findall(src)}，譯文 {MARK.findall(zh)}')
    for name, pat in [('inline code', r'`[^`\n]+`'), ('連結網址', r'\]\(([^)\s]+)'), ('src 屬性', r'src="([^"]+)"'),
                      ('錨點', r'<a id="[^"]+">')]:
        lost = set(re.findall(pat, src)) - set(re.findall(pat, zh))
        if lost:
            errs.append(f'{name} 不見或被改了：{sorted(lost)[:5]}')
    if '<!-- tutor:' in zh:
        errs.append('還留著 <!-- tutor:... --> 標記，要換成內容')
    if len(re.sub(r'\s', '', src)) > 200 and len(re.findall(r'[一-鿿]', zh)) < 30:
        errs.append('看起來沒翻成中文')
    return errs


def merge(pid):
    d = os.path.join(WORK, pid)
    meta = json.load(open(os.path.join(d, 'meta.json')))
    errs, zh_all = [], []
    for n in range(1, meta['parts'] + 1):
        src = open(os.path.join(d, f'src.{n}.md')).read()
        zp = os.path.join(d, f'zh.{n}.md')
        if not os.path.exists(zp):
            errs.append(f'缺 zh.{n}.md')
            continue
        zh = open(zp).read()
        errs += [f'zh.{n}.md：{e}' for e in check(src, zh)]
        zh_all.append(zh)
    if errs:
        print('\n'.join(errs))
        sys.exit(1)
    if meta.get('kind') == 'ipynb':
        merge_notebook(meta, ''.join(zh_all))
        print('OK', meta['doc'])
        return
    body = MARK.sub(lambda m: meta['keep'][m[0]], ''.join(zh_all))
    front = meta['front'].replace('translated: false', 'translated: true', 1)
    open(os.path.join(ROOT, meta['doc']), 'w').write(front + '\n---\n' + body)
    print('OK', meta['doc'])


if __name__ == '__main__':
    if sys.argv[1] == 'split':
        split_all()
    elif sys.argv[1] == 'split-nb':
        split_notebooks()
    else:
        merge(sys.argv[2])
