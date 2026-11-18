// Connect saved inspections, the unit list and the simulated wind farm.
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const farm = byId('farm-scene');
  const statusLabels = {damaged: '检出病害', clear: '未见病害', uncertain: '待判定'};
  const partNames = {blade:'叶片', hub:'轮毂', nacelle:'机舱', tower:'塔筒', foundation:'基础', unknown:'部位待定位'};
  let records = [];
  let selected = '';
  let view = 'overview';
  let imageLocation = null;
  let showImageLocation = false;
  let loading = false;
  let loadError = false;
  let ready = false;
  const inspections = new FarmRecords(locateRecord, clearImageLocation);
  const damageChart = new FarmDamageChart(byId('farm-damage-chart'));

  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  const active = () => location.hash.split('/')[0] === '#farm';

  function message(type, attributes = {}) {
    if (ready) farm.contentWindow.postMessage({type, ...attributes}, location.origin);
  }

  function sceneUnit(id, findings) {
    return {
      id,
      parts: findings.filter(f => f.status === 'damaged').map(f => f.part),
      clearParts: findings.filter(f => f.status === 'clear').map(f => f.part)
    };
  }

  function syncScene() {
    const image = showImageLocation ? imageLocation : null;
    const legend = byId('farm-image-legend');
    byId('farm-overview-legend').hidden = Boolean(image);
    legend.hidden = !image;
    if (image) {
      legend.textContent = image.caption;
      legend.dataset.state = image.status;
      if (image.clearCaption) {
        const clearLabel = element('span', image.clearCaption);
        clearLabel.dataset.state = 'clear';
        legend.append(clearLabel);
      }
    }
    byId('farm-show-report').hidden = !image?.unit;
    message('wd:farm', {
      selected: image ? image.unit : selected,
      units: image ? (image.unit ? [sceneUnit(image.unit, image.findings)] : [])
                   : records.map(unit => sceneUnit(unit.id, unit.parts))
    });
  }
  function setView(mode) {
    view = mode;
    for (const button of document.querySelectorAll('[data-view]')) {
      button.setAttribute('aria-pressed', String(button.dataset.view === view));
    }
    message('wd:view', {view});
  }

  function unitStatus(findings) {
    if (findings.some(part => part.status === 'damaged')) return 'damaged';
    if (findings.some(part => part.status === 'uncertain')) return 'uncertain';
    return findings.some(part => part.status === 'clear') ? 'clear' : '';
  }
  function renderUnits() {
    const list = byId('turbine-list');
    const nodes = records.map(unit => {
      const status = unitStatus(unit.parts);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'hud-unit';
      button.dataset.unit = unit.id;
      button.title = unit.id + ' · ' + (statusLabels[status] || '未评估');
      button.setAttribute('aria-pressed', String(unit.id === selected));
      button.append(element('span', unit.id, 'hud-unit-id'), element('span', statusLabels[status] || '未评估', 'unit-inspection-state ' + status));
      button.addEventListener('click', () => focusUnit(unit.id));
      return button;
    });
    // Keep the focused unit button available to keyboard users across refreshes.
    const focusId = list.contains(document.activeElement) ? document.activeElement.dataset.unit : null;
    list.replaceChildren(...nodes);
    if (focusId) nodes.find(node => node.dataset.unit === focusId)?.focus({preventScroll:true});
  }

  function render() {
    renderUnits();
    if (loadError) {
      const retry = element('button', '重新加载机组', 'farm-retry');
      retry.type = 'button';
      retry.addEventListener('click', refresh);
      byId('turbine-list').append(retry);
    }
    const suffix = selected ? '/' + selected : '';
    byId('farm-inspect').href = '#inspection' + suffix;
    byId('farm-batch').href = '/screen/batch#batch' + suffix;
    document.querySelector('[data-view="turbine"]').disabled = !selected;
    if (active()) inspections.setContext(selected);
    syncScene();
  }

  function focusUnit(id) {
    if (!records.some(unit => unit.id === id)) return;
    showImageLocation = false;
    selected = id;
    history.replaceState(null, '', '#farm/' + id);
    render();
    inspections.filterToUnit();
    setView('turbine');
  }

  function clearImageLocation(caption = '') {
    imageLocation = caption ? {unit:'', findings:[], caption, status:'uncertain'} : null;
    showImageLocation = Boolean(imageLocation);
    if (active()) syncScene();
  }

  function locateRecord(record, explicit) {
    if (!active()) return;
    const id = record.turbine_id || '';
    const findings = record.observed_parts || [];
    const status = id ? unitStatus(findings) : '';
    const namesFor = state => findings.filter(f => f.status === state)
      .map(f => partNames[f.part] || partNames.unknown).join('、');
    const clearNames = namesFor('clear');
    let caption = '本图病害待判定';
    if (!id) caption = '本图未关联机组';
    else if (status === 'damaged') caption = '本图病害 · ' + namesFor('damaged');
    else if (status === 'clear') caption = '本图未见病害 · ' + clearNames;
    const clearCaption = id && clearNames && status !== 'clear' ? '未见病害 · ' + clearNames : '';
    imageLocation = {unit:id, findings, caption, status, clearCaption};
    showImageLocation = explicit;
    const changed = selected !== id;
    selected = id;
    if (explicit) {
      history.replaceState(null, '', id ? '#farm/' + encodeURIComponent(id) : '#farm');
    } else if (changed && location.hash.startsWith('#farm/')) {
      history.replaceState(null, '', '#farm');
    }
    render();
    if (explicit) setView(id ? 'turbine' : 'overview');
    else if (changed && view === 'turbine') setView('overview');
  }

  function renderMetrics(metrics) {
    for (const id of ['total', 'week', 'high_risk']) {
      byId(id).textContent = metrics?.[id] ?? '—';
    }
    const hasRatio = metrics?.total > 0 && Number.isInteger(metrics.high_risk);
    const percent = hasRatio ? metrics.high_risk / metrics.total * 100 : 0;
    byId('risk-fill').style.width = percent + '%';
    byId('risk-ratio').textContent = hasRatio ? percent.toLocaleString('zh-CN', {maximumFractionDigits: 1}) + '%' : '—';
  }

  async function refresh() {
    if (!active() || loading) return;
    inspections.refresh();
    damageChart.refresh();
    loading = true;
    fetch('/screen/api/overview', {cache: 'no-store'})
      .then(response => response.ok ? response.json() : null)
      .then(renderMetrics).catch(() => renderMetrics(null));
    try {
      const response = await fetch('/screen/api/farm', {cache:'no-store'});
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (!Array.isArray(data.turbines)) throw new Error('missing turbines');
      records = data.turbines;
      loadError = false;
      if (selected && !records.some(unit => unit.id === selected)) {
        selected = '';
        history.replaceState(null, '', '#farm');
        setView('overview');
      }
    } catch {
      records = [];
      loadError = true;
    } finally {
      loading = false;
      if (active()) render();
    }
  }

  for (const button of document.querySelectorAll('[data-view]')) button.addEventListener('click', () => {
    const mode = button.dataset.view;
    showImageLocation = mode === 'turbine' && Boolean(selected && imageLocation?.unit === selected);
    syncScene();
    setView(mode);
  });
  byId('farm-show-report').addEventListener('click', () => byId('farm-report-panel').scrollIntoView({block:'start'}));
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== farm.contentWindow) return;
    if (event.data?.type === 'wd:ready') {
      ready = true;
      syncScene();
      setView(view);
    } else if (event.data?.type === 'wd:select') {
      focusUnit(event.data.id);
    }
  });

  function navigate() {
    const showing = active();
    document.body.classList.toggle('inspection-mode', !showing);
    byId('workbench').hidden = showing;
    byId('farm-view').hidden = !showing;
    if (!showing) {
      inspections.leave();
      return;
    }
    const destination = location.hash.split('/')[1] || '';
    const target = /^FT\d+$/.test(destination) ? destination : '';
    if (destination && !target) history.replaceState(null, '', '#farm');
    selected = target;
    inspections.enter(selected, Boolean(target));
    setView(target ? 'turbine' : 'overview');
    if (!farm.hasAttribute('src')) farm.src = farm.dataset.src;
    render();
    refresh();
  }
  window.addEventListener('hashchange', () => { navigate(); window.scrollTo(0, 0); });
  window.addEventListener('pageshow', event => { if (event.persisted) refresh(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('inspection-saved', refresh);
  // Pick up newly saved reports from other tabs while the overview stays open.
  window.setInterval(() => { if (!document.hidden) refresh(); }, 30000);
  navigate();
})();
