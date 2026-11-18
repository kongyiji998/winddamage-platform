class RecentInspections {
  constructor(container, progress) {
    this.container = container;
    this.progress = progress;
    this.revision = 0;
  }

  render(rows) {
    this.revision++;
    this.container.classList.toggle('empty', !rows.length);
    if (!rows.length) {
      this.container.textContent = '暂无评估记录';
      return;
    }
    const list = document.createElement('ul');
    list.className = 'recent-list';
    for (const row of rows.slice(0, 5)) {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = [row.turbine_id, row.image_name].filter(Boolean).join(' · ');
      const damage = document.createElement('small');
      damage.textContent = row.damage_type || '—';
      item.append(name, damage);
      list.append(item);
    }
    this.container.replaceChildren(list);
  }

  async refresh() {
    const revision = ++this.revision;
    try {
      const response = await fetch('/screen/api/records?page_size=5');
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (revision !== this.revision) return;
      if (data.stats?.avg_time > 0) this.progress.secondsPerImage = data.stats.avg_time;
      this.render(data.rows || []);
    } catch {
      if (revision === this.revision && this.container.classList.contains('empty')) {
        this.container.textContent = '最近评估暂未加载';
      }
    }
  }
}
