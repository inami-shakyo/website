// ページの表示より先に読む小さな処理：前に選んだ文字の大きさを戻す（その人のブラウザにだけ覚えている）
try { if (localStorage.getItem('fontsize') === 'large') document.documentElement.classList.add('large'); } catch (e) {}
// 動き（ふわっと出る・波線を描く）は、「動きを減らす」設定をしていない人にだけ付ける
try {
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.classList.add('motion');
  }
} catch (e) {}
