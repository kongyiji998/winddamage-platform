function renderReportTools(container, report, recordId) {
  container.replaceChildren();
  container.classList.add('report-tools');
  if (recordId) {
    const formats = document.createElement('div');
    formats.className = 'report-formats';
    const label = document.createElement('span');
    label.textContent = '导出报告';
    formats.append(label);
    for (const [format, title] of [['pdf', 'PDF'], ['md', 'Markdown'], ['csv', 'CSV']]) {
      const link = document.createElement('a');
      link.textContent = title;
      link.setAttribute('aria-label', '导出 ' + title + ' 报告');
      link.href = '/screen/api/export/' + encodeURIComponent(recordId) + '?format=' + format;
      link.download = '';
      formats.append(link);
    }
    container.append(formats);
  }
  if (!report || typeof report !== 'object') return;

  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = recordId ? '查看原始 JSON' : '查看样例 JSON';
  const raw = document.createElement('textarea');
  raw.readOnly = true;
  raw.spellcheck = false;
  raw.setAttribute('aria-label', summary.textContent);
  raw.value = JSON.stringify(report, null, 2);
  const actions = document.createElement('div');
  actions.className = 'report-copy';
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.textContent = '复制 JSON';
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(raw.value);
      status.textContent = '已复制';
    } catch {
      raw.focus();
      raw.select();
      status.textContent = '文本已选中，可手动复制';
    }
  });
  actions.append(copy, status);
  details.append(summary, raw, actions);
  container.append(details);
}
