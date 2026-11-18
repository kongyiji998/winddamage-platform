function createInspectionAlert(alert) {
  if (!alert) return null;
  const panel = document.createElement('div');
  panel.className = 'inspection-alert';
  panel.setAttribute('role', 'alert');
  panel.setAttribute('aria-atomic', 'true');
  const title = document.createElement('strong');
  title.textContent = '高风险告警';
  const reason = document.createElement('p');
  reason.textContent = alert.reasons.join('；');
  const advice = document.createElement('p');
  advice.textContent = alert.advice ? '短期处置建议 · ' + alert.advice : '报告未给出短期处置建议，请人工复核。';
  panel.append(title, reason, advice);
  return panel;
}

function renderInspectionSummary(container, risk) {
  const fields = [['优先级', risk.level], ['损伤类型', risk.type], ['置信度', risk.confidence]];
  container.replaceChildren(...fields.map(([label, value]) => {
    const badge = document.createElement('span');
    badge.textContent = label + ' · ' + (value || '—');
    if (label === '优先级' && value === '高') badge.className = 'high';
    return badge;
  }));
  const alert = createInspectionAlert(risk.alert);
  if (alert) container.prepend(alert);
}

// Keep the original fields and order from both model reports and reference annotations.
function renderInspectionReport(container, report) {
  function renderValue(value) {
    if (Array.isArray(value) && value.length) {
      const list = document.createElement('ul');
      for (const entry of value) {
        const item = document.createElement('li');
        item.append(renderValue(entry));
        list.append(item);
      }
      return list;
    }
    if (value && typeof value === 'object') {
      const fields = document.createElement('dl');
      for (const [key, entry] of Object.entries(value)) {
        const label = document.createElement('dt');
        label.textContent = key;
        const field = document.createElement('dd');
        field.append(renderValue(entry));
        fields.append(label, field);
      }
      return fields.childElementCount ? fields : document.createTextNode('—');
    }
    return document.createTextNode(value == null || value === '' ? '—' : String(value));
  }

  const sections = document.createDocumentFragment();
  for (const [key, value] of Object.entries(report)) {
    const section = document.createElement('section');
    section.className = 'report-section';
    const title = document.createElement('h3');
    title.textContent = key === '图像Caption' ? '图像描述' : key;
    const content = renderValue(value);
    section.append(title);
    if (content.nodeType === Node.TEXT_NODE) {
      const paragraph = document.createElement('p');
      paragraph.append(content);
      section.append(paragraph);
    } else {
      section.append(content);
    }
    sections.append(section);
  }
  container.replaceChildren(sections);
}
