class FarmDamageChart {
  constructor(panel) {
    this.cards = {};
    for (const card of panel.querySelectorAll('[data-chart]')) {
      this.cards[card.dataset.chart] = {
        title: card.querySelector('h3').textContent,
        summary: card.querySelector('.chart-caption small'),
        plot: card.querySelector('.chart-plot')
      };
    }
    this.status = panel.querySelector('#assessment-chart-status');
    this.periodNote = panel.querySelector('#trend-period-note');
    this.buttons = [...panel.querySelectorAll('[data-scope]')];
    this.periodButtons = [...panel.querySelectorAll('[data-period]')];
    this.period = 'daily';
    this.scope = 'all';
    this.data = null;
    this.loading = false;
    for (const button of this.periodButtons) {
      button.addEventListener('click', () => {
        this.period = button.dataset.period;
        for (const option of this.periodButtons) {
          option.setAttribute('aria-pressed', String(option === button));
        }
        if (this.data) this.drawTrend();
      });
    }
    for (const button of this.buttons) {
      button.addEventListener('click', () => {
        if (this.scope === button.dataset.scope) return;
        this.scope = button.dataset.scope;
        this.draw();
      });
    }
  }

  async refresh() {
    if (this.loading) {
      this.refreshQueued = true;
      return;
    }
    this.loading = true;
    if (!this.data) this.draw();
    try {
      const response = await fetch('/screen/api/damage-stats', {cache: 'no-store'});
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      const periods = ['daily', 'weekly'];
      if (!data.periods?.through || !periods.every(p => Array.isArray(data.periods[p]) && data.periods[p].length) ||
          !this.buttons.every(({dataset: {scope}}) => Array.isArray(data.scopes?.[scope]) &&
            data.assessments?.[scope]?.priority && periods.every(p => Array.isArray(data.assessments[scope][p]) &&
              data.assessments[scope][p].length === data.periods[p].length))) {
        throw new Error('Incomplete assessment statistics');
      }
      const unchanged = JSON.stringify(this.data) === JSON.stringify(data);
      this.data = data;
      if (!unchanged) this.draw();
    } catch {
      this.data = null;
    } finally {
      this.loading = false;
      if (!this.data) this.draw();
      if (this.refreshQueued) {
        this.refreshQueued = false;
        this.refresh();
      }
    }
  }

  node(tag, className, text) {
    const el = document.createElement(tag);
    el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  draw() {
    const label = this.scope === 'all' ? '全场' : this.scope;
    for (const button of this.buttons) {
      button.setAttribute('aria-pressed', String(button.dataset.scope === this.scope));
    }
    this.status.hidden = Boolean(this.data);
    if (!this.data) {
      for (const card of Object.values(this.cards)) {
        card.plot.replaceChildren();
        card.summary.textContent = '';
      }
      this.periodNote.textContent = '';
      this.status.textContent = this.loading ? '正在读取评估统计…' : '评估统计暂未加载';
      if (!this.loading) {
        const retry = this.node('button', 'farm-retry', '重试');
        retry.type = 'button';
        retry.addEventListener('click', () => this.refresh());
        this.status.append(retry);
      }
      return;
    }

    const counts = new Map(this.data.scopes[this.scope].map(row => [row.type, row.count]));
    const damage = this.cards.damage;
    const damageTotal = [...counts.values()].reduce((sum, value) => sum + value, 0);
    damage.summary.textContent = label + ' · ' + damageTotal + ' 处';
    if (this.data.scopes.all.length) {
      const rows = this.data.scopes.all.map(({type}) => ({type, count: counts.get(type) || 0}));
      this.bars(damage, rows, '处', '病害类型');
    } else {
      damage.plot.replaceChildren(this.node('p', 'damage-chart-state', label + '暂无已检出的病害'));
    }

    const tones = {'高': 'high', '中': 'medium', '低': 'low', '未判定': 'unknown'};
    const priorities = Object.entries(this.data.assessments[this.scope].priority)
      .filter(([name]) => name !== '未判定' || this.data.assessments.all.priority[name] > 0)
      .map(([type, count]) => ({type, count, tone: tones[type]}));
    const total = priorities.reduce((sum, row) => sum + row.count, 0);
    this.cards.priority.summary.textContent = label + ' · ' + (total ? '累计 ' + total + ' 份' : '暂无评估记录');
    this.bars(this.cards.priority, priorities, '份', '巡检优先级');
    this.drawTrend();
  }

  drawTrend() {
    const days = this.data.periods[this.period];
    const rows = this.data.assessments[this.scope][this.period].map(({total, high_risk}, i) => ({
      type: days[i].slice(5).replace('-', '/'), date: days[i], count: total, risk: high_risk
    }));
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    const label = this.scope === 'all' ? '全场' : this.scope;
    this.cards.trend.summary.textContent = label + ' · ' + (total ? '区间内 ' + total + ' 份' : '区间内暂无评估');
    this.periodNote.textContent = days[0] + ' 至 ' + this.data.periods.through +
      (this.period === 'weekly' ? '，每周从周一开始。' : '，按评估日期统计。');
    this.bars(this.cards.trend, rows, '份', this.period === 'weekly' ? '周起始日期' : '评估日期');
  }

  bars(card, rows, unit, axis) {
    const peak = rows.reduce((max, row) => Math.max(max, row.count), 1);
    const magnitude = 10 ** Math.floor(Math.log10(peak / 3));
    const step = Math.max(1, magnitude * [1, 2, 5, 10].find(n => n * magnitude >= peak / 3));
    const ceiling = Math.ceil(peak / step) * step;
    const figure = this.node('div', 'damage-figure');
    const scale = this.node('div', 'damage-scale');
    scale.style.width = (String(ceiling).length + 1) + 'ch';
    const scroller = this.node('div', 'damage-scroll');
    scroller.tabIndex = 0;
    scroller.setAttribute('role', 'region');
    scroller.setAttribute('aria-label', card.title + '，单位' + unit);
    const grid = this.node('div', 'damage-gridlines');
    scale.setAttribute('aria-hidden', 'true');
    grid.setAttribute('aria-hidden', 'true');
    for (let value = 0; value <= ceiling; value += step) {
      const tick = this.node('span', 'damage-tick', String(value));
      const rule = this.node('i', 'damage-rule');
      rule.style.bottom = tick.style.bottom = (100 * value / ceiling) + '%';
      scale.append(tick);
      grid.append(rule);
    }

    const canvas = this.node('div', 'damage-canvas');
    const trend = card === this.cards.trend;
    const categoryWidth = trend ? Math.max(2.35, .85 + 1.35 * String(peak).length) : 3.1;
    canvas.style.minWidth = (rows.length * categoryWidth) + 'em';
    const series = this.node('ul', 'damage-bars');
    const makeBar = (count, tone) => {
      const bar = this.node('div', 'damage-bar');
      if (tone) bar.classList.add(tone);
      if (!count) bar.classList.add('zero');
      bar.style.height = (100 * count / ceiling) + '%';
      bar.append(this.node('span', 'damage-value', String(count)));
      return bar;
    };
    for (const row of rows) {
      const column = this.node('li', 'damage-column');
      column.title = trend ? row.date + ' · 评估 ' + row.count + ' 份，其中高风险 ' + row.risk + ' 份'
        : row.type + ' · ' + row.count + ' ' + unit;
      column.setAttribute('aria-label', column.title);
      const track = this.node('div', 'damage-bar-track' + (trend ? ' paired' : ''));
      track.append(makeBar(row.count, row.tone));
      if (trend) track.append(makeBar(row.risk, 'high'));
      column.append(track, this.node('span', 'damage-type', row.type));
      series.append(column);
    }
    canvas.append(grid, series);
    scroller.append(canvas);
    figure.append(scale, scroller);
    card.plot.replaceChildren(this.node('p', 'damage-axis-title', unit === '处' ? '检出数（处）' : '报告数（份）'),
      figure, this.node('p', 'damage-axis-title damage-x-title', axis));
    if (trend) scroller.scrollLeft = scroller.scrollWidth;
  }
}
