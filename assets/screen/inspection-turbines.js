// Both inspection forms use the same turbine inventory as the farm overview.
class InspectionTurbinePicker {
  constructor(onChange) {
    this.select = document.getElementById('inspection-turbine');
    this.hint = document.getElementById('turbine-hint');
    this.retry = document.getElementById('retry-turbines');
    this.defaultHint = this.hint.textContent;
    this.onChange = onChange;
    this.select.addEventListener('change', onChange);
    this.retry.addEventListener('click', () => this.load());
    window.addEventListener('hashchange', () => this.selectFromLocation());
    this.load();
  }

  get value() { return this.select.value; }

  lock(busy) {
    this.select.disabled = busy || this.select.options.length < 2;
  }

  selectFromLocation() {
    const [page, id] = location.hash.slice(1).split('/');
    const formPage = document.body.classList.contains('batch-mode') ? 'batch' : 'inspection';
    if (page !== formPage || !id || this.select.disabled) return;
    const previous = this.value;
    this.select.value = id;
    if (!this.value) this.select.value = '';
    if (previous !== this.value) this.onChange();
  }

  async load() {
    this.retry.hidden = true;
    this.select.disabled = true;
    this.hint.textContent = '正在获取风场机组…';
    try {
      const response = await fetch('/screen/api/farm');
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (!data.turbines?.length) throw new Error('风场暂无机组');
      for (const {id} of data.turbines) this.select.add(new Option(id, id));
      this.hint.textContent = this.defaultHint;
      this.select.disabled = false;
      this.selectFromLocation();
    } catch {
      this.hint.textContent = '机组清单未加载';
      this.retry.hidden = false;
    }
  }
}

function renderInspectionMetadata(container, metadata, turbineId) {
  container.replaceChildren();
  if (turbineId) {
    const link = document.createElement('a');
    link.href = '/screen#farm/' + encodeURIComponent(turbineId);
    link.className = 'turbine-location';
    link.textContent = turbineId + ' · 风场定位 ↗';
    container.append(link);
  }
  const text = metadata.filter(Boolean).join(' · ');
  if (text) container.append(document.createTextNode(text));
  container.hidden = !container.hasChildNodes();
}
