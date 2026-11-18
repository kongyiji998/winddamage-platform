(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const preview = document.body.hasAttribute('data-preview');
  const progress = new InspectionProgress(byId('batch-progress'), byId('batch-elapsed'));
  const recent = new RecentInspections(byId('recent'), progress);
  const queue = [];
  let selected = -1;
  let results = [];
  let busy = false;
  const turbines = new InspectionTurbinePicker(() => {
    if (busy) return;
    resetResults();
    select(selected);
    syncControls();
    if (queue.length) readyFeedback();
  });

  function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  async function fetchOk(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response;
  }

  function syncControls() {
    turbines.lock(busy);
    byId('files').disabled = byId('drop').disabled = busy;
    byId('clear').disabled = busy || !queue.length;
    byId('run').disabled = busy || preview || !queue.length || !turbines.value;
    byId('run').textContent = busy ? '批量评估中…' : '开始批量评估';
    for (const button of byId('samples').children) button.disabled = busy;
  }

  function resetResults() {
    results = [];
    progress.reset();
    byId('batch-alert').replaceChildren();
    byId('sum').hidden = true;
    byId('export').disabled = true;
    byId('result').replaceChildren();
  }

  function emptyReport(title, hint) {
    byId('report-source').hidden = byId('report-body').hidden = true;
    byId('report-empty').hidden = false;
    byId('report-state').textContent = title;
    byId('report-hint').textContent = hint;
    byId('report-tools').replaceChildren();
    byId('details').replaceChildren();
  }

  function showReport(source, meta, risk, report, turbineId) {
    byId('report-empty').hidden = true;
    byId('report-source').hidden = byId('report-body').hidden = false;
    byId('report-source').textContent = source;
    renderInspectionMetadata(byId('report-meta'), meta, turbineId);
    renderInspectionSummary(byId('summary'), risk);
    renderInspectionReport(byId('details'), report);
  }

  async function showSelectedReport() {
    const entry = queue[selected];
    if (!entry) {
      emptyReport('等待输入图像', '选择图片并点击「开始批量评估」，也可以先查看样例标注。');
      return;
    }
    const row = results[selected];
    if (!row) {
      if (busy) {
        emptyReport('正在排队评估', '每张图片完成后即可查看报告。');
      } else if (entry.sample) {
        const {risk, json_report} = entry.sample.report;
        showReport('样例标注', [entry.name], risk, json_report);
        renderReportTools(byId('report-tools'), json_report);
      } else {
        emptyReport('等待评估结果', preview ? '预览模式下可选择样例查看参考标注。' : '点击「开始批量评估」生成这批图片的报告。');
      }
      return;
    }
    if (!row.ok) {
      emptyReport('这张图片评估失败', [row.turbine_id, entry.name, row.error || '未能生成报告'].filter(Boolean).join(' · '));
      return;
    }

    if (!row.detail) {
      emptyReport('正在读取评估报告', entry.name);
      try {
        const response = await fetchOk('/screen/api/records/' + encodeURIComponent(row.record_id));
        row.detail = await response.json();
      } catch {
        // The batch summary and CSV are still usable if a saved detail is unavailable.
      }
      if (results[selected] !== row) return;
    }
    const risk = {level: row.priority, type: row.damage_type, confidence: row.detail?.confidence,
                  alert: row.detail?.alert || row.alert};
    const meta = [entry.name, row.detail?.timestamp];
    const turbineId = row.turbine_id || row.detail?.turbine_id;
    const report = row.detail?.json_report;
    renderReportTools(byId('report-tools'), report, row.record_id);
    if (report && typeof report === 'object' && Object.keys(report).length) {
      showReport('评估结果', meta, risk, report, turbineId);
    } else {
      showReport('评估结果', meta, risk, {'报告摘要': {'构件': row.component, '损伤类型': row.damage_type, '巡检优先级': row.priority}}, turbineId);
      const note = element('p', '完整报告暂未加载。');
      const link = element('a', '前往历史记录查看');
      link.href = '/screen/history';
      note.append(link);
      byId('details').append(note);
    }
  }

  function select(index) {
    selected = index;
    const entry = queue[index];
    const image = byId('thumbnail');
    image.hidden = byId('metadata').hidden = !entry;
    if (entry) {
      image.src = entry.url;
      const info = entry.sample ? '样例' : Math.ceil(entry.file.size / 1024) + ' KB';
      byId('metadata').textContent = (index + 1) + ' / ' + queue.length + ' · ' + entry.name + ' · ' + info;
    } else {
      image.removeAttribute('src');
      byId('metadata').textContent = '';
    }
    for (const button of document.querySelectorAll('[data-queue-index]')) {
      button.setAttribute('aria-pressed', String(Number(button.dataset.queueIndex) === index));
    }
    for (const button of byId('samples').children) {
      button.setAttribute('aria-pressed', String(button.dataset.sample === entry?.sample?.id));
    }
    showSelectedReport();
  }

  function selectionButton(index) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.queueIndex = index;
    button.title = queue[index].name;
    button.addEventListener('click', () => select(index));
    return button;
  }

  function addEntries(entries) {
    resetResults();
    const first = queue.length;
    for (const entry of entries) {
      queue.push(entry);
      const button = selectionButton(queue.length - 1);
      const image = document.createElement('img');
      image.alt = '';
      image.loading = 'lazy';
      image.src = entry.sample?.image || entry.url;
      button.append(image, element('span', entry.name));
      byId('filelist').append(button);
    }
    byId('filelist').hidden = false;
    select(first);
    syncControls();
    readyFeedback();
  }

  function readyFeedback() {
    if (preview) byId('feedback').textContent = '外观预览 · 可选图或查看样例标注';
    else byId('feedback').textContent = '已选 ' + queue.length + ' 张 · ' + (turbines.value || '请选择拍摄机组后开始评估');
  }

  function addFiles(files) {
    if (busy) return;
    const images = Array.from(files).filter(file => file.type.startsWith('image/'));
    if (!images.length) {
      byId('feedback').textContent = '请选择图片文件';
      return;
    }
    addEntries(images.map(file => ({file, name: file.name, url: URL.createObjectURL(file)})));
  }

  const drop = byId('drop');
  drop.addEventListener('click', () => byId('files').click());
  byId('files').addEventListener('change', event => {
    if (event.target.files.length) addFiles(event.target.files);
    event.target.value = '';
  });
  for (const type of ['dragover', 'dragleave', 'drop']) {
    drop.addEventListener(type, event => {
      event.preventDefault();
      drop.classList.toggle('drag', type === 'dragover' && !busy);
      if (type === 'drop') addFiles(event.dataTransfer.files);
    });
  }

  function clear() {
    resetResults();
    for (const entry of queue) {
      if (entry.file) URL.revokeObjectURL(entry.url);
    }
    queue.length = 0;
    byId('filelist').replaceChildren();
    byId('filelist').hidden = true;
    select(-1);
    syncControls();
    byId('feedback').textContent = preview ? '外观预览 · 可选图或查看样例标注' : '';
  }
  byId('clear').addEventListener('click', () => {
    turbines.select.value = '';
    clear();
  });

  async function loadSamples() {
    try {
      const response = await fetchOk('/screen-assets/examples/examples.json');
      for (const sample of await response.json()) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sample';
        button.dataset.sample = sample.id;
        button.setAttribute('aria-pressed', 'false');
        button.setAttribute('aria-label', '选择' + sample.title + '样例');
        const image = document.createElement('img');
        image.src = sample.image;
        image.alt = '';
        button.append(image, element('span', sample.title));
        button.addEventListener('click', () => {
          const index = queue.findIndex(entry => entry.sample?.id === sample.id);
          if (index >= 0) select(index);
          else addEntries([{sample, name: sample.name, url: sample.original}]);
        });
        byId('samples').append(button);
      }
      syncControls();
    } catch {
      byId('samples').closest('.inspection-samples').hidden = true;
    }
  }

  function startResults() {
    byId('sum-total').textContent = queue.length;
    for (const id of ['sum-ok', 'sum-high', 'sum-fail']) byId(id).textContent = '0';
    byId('sum').hidden = false;
    const table = document.createElement('table');
    const heading = table.createTHead().insertRow();
    for (const name of ['图片', '构件', '损伤类型', '优先级', '耗时', '状态']) heading.append(element('th', name));
    const body = table.createTBody();
    byId('result').replaceChildren(table);
    return body;
  }

  function appendResult(body, row, index) {
    const tr = body.insertRow();
    const button = selectionButton(index);
    button.textContent = queue[index].name;
    button.setAttribute('aria-pressed', String(index === selected));
    tr.insertCell().append(button);
    if (row.ok) {
      const time = row.infer_time == null ? '—' : Number(row.infer_time).toFixed(1) + ' s';
      for (const value of [row.component, row.damage_type, row.priority, time]) tr.insertCell().textContent = value || '—';
    } else {
      const error = tr.insertCell();
      error.colSpan = 4;
      error.className = 'err';
      error.textContent = row.error || '未完成';
    }
    const badge = element('span', !row.ok ? '失败' : row.high_risk ? '高风险' : '未触发告警');
    badge.className = 'sc-badge ' + (row.ok && !row.high_risk ? 'ok' : 'hi');
    tr.insertCell().append(badge);
  }

  async function analyzeEntry(entry, turbineId) {
    const form = new FormData();
    form.append('turbine_id', turbineId);
    form.append('include_report', '1');
    const image = entry.file || await (await fetchOk(entry.sample.original)).blob();
    form.append('files', image, entry.name);
    const response = await fetchOk('/screen/api/batch', {method: 'POST', body: form});
    const data = await response.json();
    if (data.results?.length !== 1) throw new Error('未收到该图像的评估结果');
    return data.results[0];
  }

  byId('run').addEventListener('click', async () => {
    const turbineId = turbines.value;
    if (busy || preview || !queue.length || !turbineId) return;
    busy = true;
    syncControls();
    resetResults();
    showSelectedReport();
    progress.start(queue.length);
    const body = startResults();
    let ok = 0, high = 0;
    try {
      for (const [index, entry] of queue.entries()) {
        byId('feedback').textContent = '正在评估 ' + (index + 1) + ' / ' + queue.length + ' · ' + entry.name;
        let row;
        try {
          row = await analyzeEntry(entry, turbineId);
        } catch (error) {
          row = {ok: false, filename: entry.name, turbine_id: turbineId, error: '未收到报告，请核对历史记录 · ' + error.message};
        }
        results.push(row);
        appendResult(body, row, index);
        if (row.ok) ok++;
        if (row.high_risk) {
          high++;
          const alert = createInspectionAlert(row.alert);
          if (alert) {
            alert.querySelector('strong').textContent = '高风险告警 · ' + entry.name;
            byId('batch-alert').replaceChildren(alert);
          }
        }
        byId('sum-ok').textContent = ok;
        byId('sum-high').textContent = high;
        byId('sum-fail').textContent = results.length - ok;
        progress.imageFinished(results.length);
        if (selected === index) showSelectedReport();
      }
      progress.complete();
      recent.refresh();
      byId('feedback').textContent = '批量评估完成 · 成功 ' + ok + ' 张 · 高风险 ' + high + ' 张 · 失败 ' + (results.length - ok) + ' 张';
    } finally {
      busy = false;
      syncControls();
      byId('export').disabled = !results.length;
    }
  });

  byId('export').addEventListener('click', () => {
    const rows = [['图片', '构件', '损伤类型', '优先级', '风险', '耗时(s)', '记录ID', '错误', '拍摄机组']];
    for (const row of results) {
      rows.push([row.filename, row.component, row.damage_type, row.priority,
        row.ok ? (row.high_risk ? '高风险' : '未触发告警') : '', row.infer_time, row.record_id, row.error, row.turbine_id]);
    }
    const quote = cell => '"' + String(cell ?? '').replace(/"/g, '""') + '"';
    const csv = '\uFEFF' + rows.map(row => row.map(quote).join(',')).join('\r\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    link.download = 'batch_' + new Date().toISOString().slice(0, 10) + '.csv';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });

  clear();
  recent.refresh();
  loadSamples();
})();
