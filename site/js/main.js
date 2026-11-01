// 稲美町社会福祉協議会 ホームページ（試作）の動き：メニュー開閉・文字サイズ・お知らせの絞り込み・NEW表示
(function () {
  var root = document.documentElement;

  // ふわっと出てくる動き：トップの見出し・カード・ご案内・お知らせ・関係機関を、画面に入ったものから順に出す
  // （隠す印 .rv はこの処理が付けるので、この処理が動かなければ最初から全部見えている）
  if (root.classList.contains('motion')) {
    var groups = ['.sec', '.cards > *', '.igrid > *', '#home-news > li', '.banner-list > li'];
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('shown'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    groups.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (el, i) {
        el.classList.add('rv');
        el.style.transitionDelay = Math.min(i, 6) * 0.08 + 's'; // 並んでいるものは少しずつずらして出す
        io.observe(el);
      });
    });
  }

  // スマホのメニュー
  var menuBtn = document.querySelector('.menu-toggle');
  var nav = document.getElementById('gnav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      menuBtn.textContent = open ? '閉じる' : 'メニュー';
    });
  }

  // 文字サイズ（選んだ大きさは、その人のブラウザにだけ覚えておく）
  var fsBtn = document.querySelector('.fs-toggle');
  function syncFs() {
    var large = root.classList.contains('large');
    if (fsBtn) {
      fsBtn.setAttribute('aria-pressed', large ? 'true' : 'false');
      fsBtn.textContent = large ? '文字を標準に' : '文字を大きく';
    }
  }
  if (fsBtn) {
    fsBtn.addEventListener('click', function () {
      var large = root.classList.toggle('large');
      try { localStorage.setItem('fontsize', large ? 'large' : 'normal'); } catch (e) {}
      syncFs();
    });
    syncFs();
  }

  // NEW 表示：掲載から14日以内（見た日を基準に毎回計算するので、古いNEWが残らない）
  var now = new Date();
  document.querySelectorAll('.news-list li[data-date]').forEach(function (li) {
    var d = new Date(li.getAttribute('data-date') + 'T00:00:00');
    if ((now - d) / 86400000 <= 14) {
      var s = document.createElement('span');
      s.className = 'new';
      s.textContent = 'NEW';
      (li.querySelector('.news-title') || li).appendChild(s);
    }
  });

  // お知らせの種類で絞り込む（上の「すべて／ニュース／募集／災害支援」と、各お知らせの種類の札の両方から）
  document.querySelectorAll('.tabs').forEach(function (tabs) {
    var list = document.getElementById(tabs.getAttribute('data-target'));
    if (!list) return;
    var empty = list.nextElementSibling;
    function apply(f) {
      tabs.querySelectorAll('button').forEach(function (x) {
        x.setAttribute('aria-selected', x.getAttribute('data-filter') === f ? 'true' : 'false');
      });
      var shown = 0;
      list.querySelectorAll('li').forEach(function (li) {
        var ok = f === 'all' || li.getAttribute('data-cat') === f;
        li.hidden = !ok;
        if (ok) shown++;
      });
      if (empty && empty.classList.contains('empty')) empty.hidden = shown > 0;
    }
    tabs.addEventListener('click', function (ev) {
      var b = ev.target.closest('button');
      if (b) apply(b.getAttribute('data-filter'));
    });
    list.addEventListener('click', function (ev) {
      var b = ev.target.closest('button.cat');
      if (!b) return;
      apply(b.getAttribute('data-filter'));
      tabs.scrollIntoView({ block: 'nearest' });
    });
    var q = (location.search.match(/[?&]cat=([a-z]+)/) || [])[1];   // お知らせのページの札から来たとき
    if (q && tabs.querySelector('[data-filter="' + q + '"]')) apply(q);
  });
})();
