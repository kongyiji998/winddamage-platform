(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const preview = document.body.hasAttribute('data-preview');
  const element = (tag, text) => {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
  };
  const status = text => { byId('feedback').textContent = text; };
  const defaultFeedback = preview ? '外观预览 · 可选图或查看样例标注' : '';
  const getJSON = async (url, options) => {
    const response = await fetch(url, options);
    if (response.status === 422) {
      const body = await response.json();
      const error = new Error(body.detail);
      error.status = response.status;
      throw error;
    }
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  };
  let selection = null;
  let objectUrl = '';
  let controller = null;
  const progress = new InspectionProgress(byId('analysis-progress'), byId('analysis-elapsed'));
  const recent = new RecentInspections(byId('recent'), progress);
  const turbines = new InspectionTurbinePicker(turbineChanged);
  recent.refresh();
  function showEmptyReport(message, hint) {
    byId('report-body').hidden = true;
    byId('report-empty').hidden = false;
    byId('report-state').textContent = message;
    byId('report-hint').textContent = hint;
    byId('report-source').hidden = true;
    byId('report-tools').replaceChildren();
    byId('details').replaceChildren();
  }
  function showReport(data, sample) {
    byId('report-empty').hidden = true;
    byId('report-body').hidden = false;
    byId('report-source').hidden = false;
    byId('report-source').textContent = sample ? '样例标注' : '评估结果';
    renderInspectionSummary(byId('summary'), data.risk);
    if (data.json_report && typeof data.json_report === 'object' && Object.keys(data.json_report).length) {
      renderInspectionReport(byId('details'), data.json_report);
    } else {
      renderInspectionReport(byId('details'), {'报告摘要': {'构件':data.kv.component, '损伤位置':data.kv.location, '处置建议':data.kv.advice}});
      if (!sample) {
        const note = element('p', '完整报告暂未加载。');
        const historyLink = element('a', '前往历史记录查看');
        historyLink.href = '/screen/history';
        note.append(historyLink);
        byId('details').append(note);
      }
    }
    const metadata = sample ? [] : [data.kv.report_no, data.kv.model, data.kv.time];
    renderInspectionMetadata(byId('report-meta'), metadata, sample ? null : data.turbine_id);
    renderReportTools(byId('report-tools'), data.json_report, sample ? null : data.record_id);
    if (!sample && data.recent) recent.render(data.recent);
  }
  function reset() {
    if (controller) controller.abort();
    controller = null;
    turbines.lock(false);
    progress.reset();
    selection = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = '';
    byId('file').value = '';
    byId('thumbnail').hidden = true;
    byId('thumbnail').removeAttribute('src');
    byId('metadata').hidden = true;
    byId('analyze').disabled = true;
    byId('analyze').textContent = '开始评估';
    byId('clear').disabled = true;
    document.querySelectorAll('.sample').forEach(b => b.setAttribute('aria-pressed','false'));
    showEmptyReport('等待评估结果', '选择图片后点击「开始评估」，也可以先查看样例标注。');
    status(defaultFeedback);
  }
  function updateReadyState() {
    byId('analyze').disabled = preview || !selection || !turbines.value;
    if (!selection) return;
    if (preview) {
      status(selection.sample ? '正在查看样例标注' : '已选图 · 当前预览未启用模型评估');
    } else {
      status(turbines.value ? '待评估机组 · ' + turbines.value : '请选择拍摄机组后开始评估');
    }
  }
  function turbineChanged() {
    if (controller) return;
    progress.reset();
    if (selection?.sample) showReport(selection.sample.report, true);
    else if (selection) showEmptyReport('等待评估结果', '点击「开始评估」生成当前机组的评估报告。');
    updateReadyState();
  }
  function showImage(url, description) {
    const img = byId('thumbnail');
    img.src = url;
    img.hidden = false;
    byId('clear').disabled = false;
    byId('metadata').hidden = false;
    byId('metadata').textContent = description;
  }
  function chooseSample(sample) {
    reset();
    for (const item of document.querySelectorAll('#samples .sample')) {
      item.setAttribute('aria-pressed', String(item.dataset.sample === sample.id));
    }
    selection = {sample};
    showImage(sample.original, '样例 · ' + sample.name);
    showReport(sample.report, true);
    updateReadyState();
  }
  window.addEventListener('farm-sample-inspect', event => {
    chooseSample(event.detail);
    location.hash = byId('farm-inspect').hash;
  });
  function sampleButton(sample) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sample';
    button.dataset.sample = sample.id;
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', '查看' + sample.title + '样例标注');
    const img = document.createElement('img');
    img.alt = '';
    img.src = sample.image;
    const priority = sample.report.risk.level;
    if (priority === '高') button.classList.add('is-high');
    button.append(img, element('span', sample.title), element('small', priority + '优先级'));
    button.addEventListener('click', () => chooseSample(sample));
    return button;
  }
  getJSON('/screen-assets/examples/examples.json').then(items => {
    for (const sample of items) {
      byId('samples').append(sampleButton(sample));
    }
  }).catch(() => { document.querySelectorAll('.sample-block').forEach(block => { block.hidden = true; }); });
  function pick(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { status('请选择图片文件'); return; }
    reset();
    selection = {file};
    objectUrl = URL.createObjectURL(file);
    showImage(objectUrl,file.name + ' · ' + Math.ceil(file.size/1024) + ' KB');
    byId('report-hint').textContent = preview ? '预览模式下可选择样例查看参考标注。' : '点击“开始评估”生成这张图片的报告。';
    updateReadyState();
  }
  const drop = byId('drop');
  drop.addEventListener('click',() => byId('file').click());
  byId('file').addEventListener('change',e => pick(e.target.files[0]));
  for (const event of ['dragover','dragleave','drop']) drop.addEventListener(event,e => {
    e.preventDefault();
    drop.classList.toggle('drag',event === 'dragover');
    if (event === 'drop') pick(e.dataTransfer.files[0]);
  });
  byId('clear').addEventListener('click', () => {
    turbines.select.value = '';
    reset();
  });
  byId('analyze').addEventListener('click',async () => {
    const turbineId = turbines.value;
    if (!selection || preview || controller || !turbineId) return;
    const current = controller = new AbortController();
    turbines.lock(true);
    byId('analyze').disabled = true;
    byId('analyze').textContent = '评估中…';
    showEmptyReport('正在生成报告', '模型正在评估当前图片，完成后会在这里显示结果。');
    progress.start();
    const {file, sample} = selection;
    try {
      const form = new FormData();
      form.append('turbine_id', turbineId);
      if (sample) {
        status('正在读取样例原图');
        const response = await fetch(sample.original, {signal:current.signal});
        if (!response.ok) throw new Error(String(response.status));
        form.append('file', await response.blob(), sample.name);
      } else {
        form.append('file', file);
      }
      if (controller !== current) return;
      status('正在评估 ' + turbineId + ' 的图像');
      const data = await getJSON('/screen/api/analyze',{method:'POST',body:form,signal:current.signal});
      if (controller !== current) return;
      // Servers started before the full-report response was added still expose it in history.
      if (!data.json_report && data.record_id) {
        try {
          const record = await getJSON('/screen/api/records/' + encodeURIComponent(data.record_id),
                                       {signal:current.signal});
          data.json_report = record.json_report;
        } catch {
          // The saved analysis can still be displayed and exported from its summary response.
        }
        if (controller !== current) return;
      }
      showReport(data,false);
      const meta = data.image_info;
      if (meta?.meta) byId('metadata').textContent = [meta.filename,meta.meta].join(' · ');
      progress.complete();
      status(data.risk.alert ? '评估完成 · 已触发高风险告警，请查看处置建议' : '评估完成');
      window.dispatchEvent(new Event('inspection-saved'));
    } catch (error) {
      if (controller === current) {
        progress.reset();
        status('评估失败，请重试');
        const reason = error.status === 422 ? error.message : '';
        showEmptyReport('未能生成报告', reason + '当前图片已保留，可重新点击“开始评估”。');
      }
    } finally {
      if (controller === current) {
        controller = null;
        turbines.lock(false);
        byId('analyze').disabled = false;
        byId('analyze').textContent = '开始评估';
      }
    }
  });
  reset();
})();
