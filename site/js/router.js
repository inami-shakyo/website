// 旧サイトのアドレス page1.html?id=○ を、新しいページへ案内する
(function () {
  var id = (location.search.match(/[?&]id=(\d+)/) || [])[1];
  var map = { "7": "page1_id7.html", "8": "page1_id8.html", "16": "page1_id16.html" };
  location.replace(map[id] || "./");
})();
