// サイト内の検索：書き出しのときに作った search.json（ページとお知らせの題・本文）を読んで、見る人のブラウザの中だけで探す。
// 外のサービスには何も送らない。結果は文字として組み立て、HTMLとしては扱わない（書き込まれた言葉で画面がこわれないように）。
(function () {
  var params = new URLSearchParams(location.search);
  var q = (params.get('q') || '').trim().slice(0, 40);
  var input = document.getElementById('q');
  var count = document.querySelector('.search-count');
  var list = document.querySelector('.search-results');
  if (!input || !count || !list) return;
  input.value = q;
  document.querySelectorAll('.hsearch input[name="q"]').forEach(function (el) { el.value = q; });
  if (!q) { input.focus(); return; }

  // 全角・半角、大文字・小文字、カタカナ・ひらがなの違いを気にせず探す（1字ずつ置きかえ、字数を変えない）
  function norm(s) {
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      var n = c.normalize('NFKC');
      if (n.length === 1) c = n;
      c = c.toLowerCase();
      var code = c.charCodeAt(0);
      if (code >= 0x30a1 && code <= 0x30f6) c = String.fromCharCode(code - 0x60);
      out += c;
    }
    return out;
  }
  var terms = norm(q).split(/[\s　]+/).filter(function (t) { return t; });

  function snippet(text, ntext) {
    var at = -1;
    terms.forEach(function (t) { var i = ntext.indexOf(t); if (i >= 0 && (at < 0 || i < at)) at = i; });
    if (at < 0) return null;
    var start = Math.max(0, at - 40), end = Math.min(text.length, at + 90);
    var frag = document.createDocumentFragment();
    if (start > 0) frag.appendChild(document.createTextNode('…'));
    var part = text.slice(start, end), npart = ntext.slice(start, end), k = 0;
    while (k < part.length) {
      var hit = null;
      terms.forEach(function (t) { if (!hit && npart.substr(k, t.length) === t) hit = t; });
      if (hit) {
        var m = document.createElement('mark');
        m.textContent = part.substr(k, hit.length);
        frag.appendChild(m);
        k += hit.length;
      } else {
        var j = k + 1;
        frag.appendChild(document.createTextNode(part[k]));
        k = j;
      }
    }
    if (end < text.length) frag.appendChild(document.createTextNode('…'));
    return frag;
  }

  function show(rows) {
    var found = [];
    rows.forEach(function (r) {
      var nt = norm(r.t), nx = norm(r.x || '');
      var all = terms.every(function (t) { return nt.indexOf(t) >= 0 || nx.indexOf(t) >= 0; });
      if (!all) return;
      var score = 0;
      terms.forEach(function (t) {
        if (nt.indexOf(t) >= 0) score += 10;
        score += Math.min(5, nx.split(t).length - 1);
      });
      found.push({ r: r, nx: nx, score: score });
    });
    found.sort(function (a, b) { return b.score - a.score || (b.r.d || '').localeCompare(a.r.d || ''); });
    count.textContent = found.length
      ? '「' + q + '」が見つかったのは ' + found.length + ' 件です。' + (found.length > 50 ? '（はじめの50件を出しています）' : '')
      : '「' + q + '」は見つかりませんでした。言葉を短くするか、別の言い方で探してみてください。お電話でもお尋ねいただけます。';
    found.slice(0, 50).forEach(function (f) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = f.r.u;
      a.textContent = f.r.t;
      if (f.r.o) { a.target = '_blank'; a.rel = 'noopener'; }
      var h = document.createElement('p');
      h.className = 'r-title';
      h.appendChild(a);
      if (f.r.d) {
        var d = document.createElement('span');
        d.className = 'r-date';
        var p = f.r.d.split('-');
        d.textContent = 'お知らせ　' + Number(p[0]) + '年' + Number(p[1]) + '月' + Number(p[2]) + '日';
        h.appendChild(d);
      }
      li.appendChild(h);
      var sn = f.r.x ? snippet(f.r.x, f.nx) : null;
      if (sn) {
        var s = document.createElement('p');
        s.className = 'r-text';
        s.appendChild(sn);
        li.appendChild(s);
      }
      list.appendChild(li);
    });
  }

  count.textContent = '探しています…';
  fetch('search.json').then(function (r) { return r.json(); }).then(show).catch(function () {
    count.textContent = '検索の準備ができませんでした。時間をおいてもう一度お試しください。';
  });
})();
