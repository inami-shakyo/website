// 見つからないページ：旧サイトのアドレス（PHP・管理画面のPDF）で来た人を、新しい場所へ案内する
(function () {
  var p = location.pathname, q = location.search, m = q.match(/[?&]file=([^&]+)/), to = null;
  if (/\/kanri\/(download|output)\.php$/.test(p) && m) to = "/files/" + decodeURIComponent(m[1]);
  else if (/\/kanri\/image\.php$/.test(p) && m) to = "/img/old/" + decodeURIComponent(m[1]);
  else if (/\/topics_index\.php$/.test(p)) to = "/topics_index.html";
  else if (/\/inquiry\.php$/.test(p)) to = "/inquiry.html";
  if (to) { location.replace(to); return; }
  // 社協だよりなどの二次元コードから、掲載を終えたお知らせ（topics_○○.html）に来た人への案内
  if (/\/topics_\d+\.html$/.test(p)) {
    document.addEventListener("DOMContentLoaded", function () {
      var h = document.querySelector(".notfound h1"), t = document.querySelector(".notfound p");
      if (h) h.textContent = "このお知らせは、掲載を終えました";
      if (t) t.textContent = "催しが終わったなどの理由で、このお知らせはホームページから下げています。新しいお知らせは、一覧からご覧ください。";
    });
  }
})();
