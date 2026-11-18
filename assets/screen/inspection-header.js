(() => {
  'use strict';
  const header = document.getElementById('inspection-header');
  const page = header.dataset.page;
  const home = page === 'single' ? '' : '/screen';
  const titleTag = page === 'history' ? 'p' : 'h1';
  header.innerHTML = `
    <${titleTag} class="system-title"><a href="/screen"><span>基于多模态大模型的</span><span>风电塔灾损测算平台</span></a></${titleTag}>
    <nav aria-label="主要导航">
      <a href="${home}#farm" id="home-link">风场总览</a>
      <details class="inspection-menu">
        <summary>开始评估</summary>
        <div class="inspection-subnav">
          <a href="${home}#inspection" id="inspection-link">单图评估</a>
          <a href="/screen/batch" id="batch-link">批量评估</a>
        </div>
      </details>
      <a href="/screen/history" id="history-link">历史记录</a>
    </nav>
    <div class="header-time">
      <div class="header-clock"><time id="clock"></time><span id="date"></span></div>
      <div class="header-user"><span id="user"></span>
        <a class="account-link" href="/screen/account" hidden>账户</a>
        <a class="account-link" href="/logout" hidden>退出</a>
      </div>
    </div>`;

  function updateNavigation() {
    const onFarm = page === 'single' && location.hash.split('/')[0] === '#farm';
    const current = onFarm ? 'home-link' : {single:'inspection-link', batch:'batch-link', history:'history-link'}[page];
    for (const link of header.querySelectorAll('nav a[id]')) {
      if (link.id === current) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }
  updateNavigation();
  window.addEventListener('hashchange', updateNavigation);

  const time = document.getElementById('clock');
  const date = document.getElementById('date');
  const timeFormat = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false});
  const dateFormat = new Intl.DateTimeFormat('zh-CN', {year:'numeric', month:'long', day:'numeric', weekday:'long'});
  function updateClock() {
    const now = new Date();
    time.textContent = timeFormat.format(now);
    date.textContent = dateFormat.format(now);
  }
  updateClock();
  window.setInterval(updateClock, 1000);

  fetch('/screen/api/me').then(response => {
    if (response.ok) return response.json();
  }).then(user => {
    if (!user) return;
    const username = document.getElementById('user');
    username.textContent = user.role === 'local' ? '本机评估' : user.username || '';
    username.title = username.textContent;
    if (user.role === 'user' || user.role === 'admin') {
      for (const link of header.querySelectorAll('.account-link')) link.hidden = false;
    }
  }).catch(() => {});
})();
