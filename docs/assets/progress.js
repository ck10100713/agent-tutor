// 閱讀紀錄：存在這個瀏覽器的 localStorage，換瀏覽器或清除網站資料就會不見
(() => {
  const READ = 'tutor:read';  // { 頁面路徑: 最後閱讀時間 }
  const LAST = 'tutor:last';  // { path, title }：首頁的「繼續閱讀」
  const load = (k, fallback) => {
    try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch { return fallback; }
  };
  const save = (k, v) => {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 無痕模式等情況存不了就算了 */ }
  };

  function update() {
    const read = load(READ, {});
    const box = document.getElementById('tutor-continue');  // 只有首頁有
    if (!box) {
      read[location.pathname] = Date.now();
      save(READ, read);
      save(LAST, { path: location.pathname, title: document.title.split(' - ')[0] });
    }

    // 側邊欄：讀過的打勾（帶 # 的是頁內段落目錄，不算）
    document.querySelectorAll('.md-nav__link[href]').forEach(a => {
      const url = new URL(a.href, location.href);
      a.classList.toggle('tutor-read', url.origin === location.origin && !url.hash && url.pathname in read);
    });

    const last = load(LAST, null);
    if (box && last) {
      const link = document.createElement('a');
      link.href = last.path;
      link.textContent = last.title;  // 用 textContent，標題不會被當成 HTML
      box.replaceChildren('繼續閱讀：', link, `・已讀 ${Object.keys(read).length} 篇`);
    }
  }

  // Material 的 document$ 在每次換頁都會觸發；沒有的話退回一般的載入事件
  if (window.document$) window.document$.subscribe(update);
  else document.addEventListener('DOMContentLoaded', update);
})();
