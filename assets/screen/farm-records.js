// The overview reads the same permission-scoped history as the inspection workbench.
class FarmRecords {
  constructor(onPickTurbine, clearImageLocation) {
    this.onPickTurbine = onPickTurbine;
    this.clearImageLocation = clearImageLocation;
    this.filter = document.getElementById('farm-record-filter');
    this.list = document.getElementById('farm-record-list');
    this.detail = document.getElementById('farm-record-detail');
    this.source = document.getElementById('farm-record-source');
    this.filter.addEventListener('change', () => this.resetList());
    this.list.addEventListener('scroll', () => this.loadMoreIfNeeded(), {passive: true});
    this.unit = null;
    this.pageSize = 24;
    this.rows = [];
    this.total = 0;
    this.selectedKey = '';
    this.listRequest = null;
    this.detailRequest = null;
    this.samples = null;
  }

  enter(unit, specific) {
    this.unit = unit;
    this.filter.value = specific ? 'current' : document.body.hasAttribute('data-preview') ? 'samples' : 'all';
    this.resetList();
  }

  leave() {
    this.listRequest?.abort();
    this.unit = null;
    this.clearDetail('');
  }

  setContext(unit) {
    if (this.unit === null || this.unit === unit) return;
    this.unit = unit;
    if (this.filter.value === 'current') this.resetList();
  }

  filterToUnit() {
    if (this.filter.value === 'current') return;
    this.filter.value = 'current';
    this.resetList();
  }

  resetList() {
    this.listRequest?.abort();
    this.rows = [];
    this.total = 0;
    this.list.scrollTop = 0;
    this.clearDetail('正在读取评估报告…');
    this.list.replaceChildren(this.node('p', '正在读取图片…', 'farm-record-message'));
    this.loadList();
  }

  refresh() {
    if (this.unit !== null && !this.listRequest) this.loadList();
  }

  loadMoreIfNeeded() {
    if (this.unit === null || this.listRequest || this.rows.length >= this.total || this.list.querySelector('.farm-retry')) return;
    if (this.list.clientHeight && this.list.scrollHeight - this.list.scrollTop - this.list.clientHeight < 140) {
      this.loadList(true);
    }
  }

  node(tag, text, className) {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  button(text, onClick) {
    const button = this.node('button', text);
    button.type = 'button';
    button.addEventListener('click', onClick);
    return button;
  }

  async json(url, request) {
    const response = await fetch(url, {signal: request.signal, cache: 'no-store'});
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  async loadList(append = false) {
    const request = new AbortController();
    this.listRequest = request;
    const filter = this.filter.value;
    const isSample = filter === 'samples';
    this.list.setAttribute('aria-busy', 'true');
    this.list.querySelector('.farm-retry')?.remove();
    const previous = this.rows;
    const fetchPage = (page, size) => {
      const params = new URLSearchParams({page, page_size: size});
      if (filter === 'current') params.set('turbine_id', this.unit);
      if (filter === 'unassigned') params.set('turbine_id', 'unassigned');
      return this.json('/screen/api/records?' + params, request);
    };
    try {
      let rows = [], total = 0;
      if (isSample) {
        const samples = this.samples || await this.json('/screen-assets/examples/examples.json', request);
        if (!Array.isArray(samples)) throw new Error('invalid samples');
        this.samples = samples;
        rows = samples;
        total = samples.length;
      } else if (filter !== 'current' || this.unit) {
        const page = append ? previous.length / this.pageSize + 1 : 1;
        const loadedPages = Math.max(1, Math.ceil(previous.length / this.pageSize));
        const size = append ? this.pageSize : loadedPages * this.pageSize;
        let data = await fetchPage(page, size);
        if (request.signal.aborted) return;
        if (!Array.isArray(data.rows) || !Number.isInteger(data.total)) throw new Error('invalid records');
        // Inserts or deletions can move the offset since the previous scroll.
        // Reread the displayed range so numbering and the selected image stay together.
        const growth = Math.max(0, data.total - this.total);
        const oldTail = previous.at(-1)?.id;
        const overlap = append && data.rows.some(row => previous.some(loaded => loaded.id === row.id));
        const tailMoved = !append && growth && data.rows.length < data.total && !data.rows.some(row => row.id === oldTail);
        if (previous.length && ((append && data.total !== this.total) || overlap || tailMoved)) {
          const needed = previous.length + growth + (append ? this.pageSize : 0);
          data = await fetchPage(1, Math.ceil(needed / this.pageSize) * this.pageSize);
          append = false;
        }
        rows = append ? previous.concat(data.rows) : data.rows;
        total = data.total;
      }
      if (request.signal.aborted) return;
      this.rows = rows;
      this.total = total;
      if (append) {
        this.list.append(...rows.slice(previous.length).map((row, index) =>
          this.rowButton(row, false, previous.length + index + 1)));
      } else if (!previous.length || JSON.stringify(previous) !== JSON.stringify(rows)) {
        const focusedKey = document.activeElement.dataset.key;
        const top = this.list.getBoundingClientRect().top;
        const firstVisible = this.list.scrollTop > 0 && [...this.list.children].find(row => row.getBoundingClientRect().bottom > top);
        const offset = firstVisible && firstVisible.getBoundingClientRect().top - top;
        this.list.replaceChildren(...rows.map((row, i) => this.rowButton(row, isSample, i + 1)));
        if (!rows.length) this.list.append(this.node('p', '此范围暂无已评估图片', 'farm-record-message'));
        if (!rows.length) {
          const scope = filter === 'current' && this.unit ? this.unit : '当前范围';
          this.clearDetail(scope + '暂无评估报告。');
        } else if (![...this.list.children].some(item => item.dataset.key === this.selectedKey)) {
          if (isSample) this.openSample(rows[0], false);
          else this.openRecord(rows[0].id, false);
        } else {
          this.markSelected();
        }
        if (firstVisible) {
          const anchor = [...this.list.children].find(row => row.dataset.key === firstVisible.dataset.key);
          if (anchor) this.list.scrollTop += anchor.getBoundingClientRect().top - top - offset;
        }
        if (focusedKey) [...this.list.children].find(node => node.dataset.key === focusedKey)?.focus({preventScroll: true});
      }
      requestAnimationFrame(() => this.loadMoreIfNeeded());
    } catch {
      if (!request.signal.aborted) {
        if (!previous.length) this.list.replaceChildren(this.node('p', '图片列表暂未加载', 'farm-record-message'));
        const retry = this.button('重新加载图片', () => this.loadList(append));
        retry.className = 'farm-retry';
        this.list.append(retry);
        if (!this.selectedKey) this.clearDetail('评估列表暂未加载，请在左侧重新读取。');
      }
    } finally {
      if (this.listRequest === request) {
        this.listRequest = null;
        this.list.removeAttribute('aria-busy');
      }
    }
  }

  rowButton(row, sample, number) {
    const button = this.button('', () => sample ? this.openSample(row) : this.openRecord(row.id));
    button.className = 'farm-record-row';
    button.dataset.key = (sample ? 'sample-' : 'record-') + row.id;
    button.setAttribute('aria-pressed', String(button.dataset.key === this.selectedKey));
    if (sample) button.dataset.sampleId = row.id;
    else button.dataset.recordId = row.id;
    const imageUrl = sample ? row.image : this.imageUrl(row);
    const missing = this.node('span', '报告', 'farm-record-placeholder');
    missing.setAttribute('aria-hidden', 'true');
    const text = this.node('span', null, 'farm-record-text');
    const name = sample ? row.name : row.image_name;
    const caption = sample ? '样例标注 · ' + row.title :
      [row.turbine_id || '未关联机组', row.timestamp?.slice(0, 16)].filter(Boolean).join(' · ');
    text.append(this.node('strong', name), this.node('small', caption));
    if (sample ? row.report.risk.alert : row.high_risk) {
      text.append(this.node('small', '高风险', 'farm-record-risk'));
    }
    button.append(this.node('span', String(number), 'farm-record-number'), text);
    if (imageUrl) {
      const img = this.node('img');
      img.alt = '';
      img.loading = 'lazy';
      img.addEventListener('error', () => img.replaceWith(missing), {once: true});
      img.src = imageUrl;
      button.append(img);
    } else {
      button.append(missing);
    }
    button.title = name + ' · ' + caption;
    return button;
  }

  imageUrl(row) {
    return row.image_file_id ? '/history/' + encodeURIComponent(row.id) + '/image' : '';
  }

  markSelected() {
    for (const row of this.list.querySelectorAll('button[data-key]')) {
      row.setAttribute('aria-pressed', String(row.dataset.key === this.selectedKey));
    }
  }

  clearDetail(message) {
    this.clearImageLocation();
    this.detailRequest?.abort();
    this.detailRequest = null;
    this.selectedKey = '';
    this.markSelected();
    this.detail.replaceChildren(this.node('p', message, 'farm-record-message'));
    this.source.textContent = '';
    this.detail.removeAttribute('aria-busy');
    delete this.detail.dataset.recordId;
    delete this.detail.dataset.sampleId;
  }

  revealDetail() {
    if (window.matchMedia('(max-width:680px)').matches) {
      document.getElementById('farm-report-panel').scrollIntoView({block:'start'});
    }
  }

  beginDetail(key) {
    this.detailRequest?.abort();
    this.detailRequest = null;
    this.selectedKey = key;
    this.markSelected();
    delete this.detail.dataset.recordId;
    delete this.detail.dataset.sampleId;
    this.detail.scrollTop = 0;
  }

  async openRecord(id, explicit = true) {
    this.beginDetail('record-' + id);
    this.detail.dataset.recordId = id;
    this.detail.setAttribute('aria-busy', 'true');
    this.source.textContent = '记录 #' + id;
    this.detail.replaceChildren(this.node('p', '正在读取评估报告…', 'farm-record-message'));
    this.clearImageLocation(explicit ? '正在读取本图定位…' : '');
    const request = new AbortController();
    this.detailRequest = request;
    try {
      const record = await this.json('/screen/api/records/' + encodeURIComponent(id), request);
      if (request.signal.aborted) return;
      const metadata = [record.turbine_id || '未关联机组', record.timestamp];
      if (record.infer_time != null) metadata.push('用时 ' + Number(record.infer_time).toFixed(1) + ' 秒');
      this.renderDetail({
        name: record.image_name, label: '记录 #' + record.id, metadata,
        url: this.imageUrl(record),
        risk: {level: record.priority, type: record.damage_type, confidence: record.confidence, alert: record.alert},
        report: record.json_report, recordId: record.id
      });
      this.onPickTurbine(record, explicit);
      if (explicit && window.matchMedia('(max-width:680px)').matches) {
        if (record.turbine_id) document.querySelector('.farm-viewport').scrollIntoView({block:'start'});
        else this.revealDetail();
      }
    } catch {
      if (!request.signal.aborted) {
        this.clearImageLocation(explicit ? '本图定位暂不可用' : '');
        this.detail.replaceChildren(this.node('p', '评估报告暂未加载', 'farm-record-message'),
          this.button('重新读取', () => this.openRecord(id, explicit)));
      }
    } finally {
      if (this.detailRequest === request) {
        this.detailRequest = null;
        this.detail.removeAttribute('aria-busy');
      }
    }
  }

  openSample(sample, explicit = true) {
    this.beginDetail('sample-' + sample.id);
    this.onPickTurbine({}, explicit);
    this.detail.removeAttribute('aria-busy');
    this.detail.dataset.sampleId = sample.id;
    const action = this.button('使用此图评估', () => {
      window.dispatchEvent(new CustomEvent('farm-sample-inspect', {detail: sample}));
    });
    this.renderDetail({
      name: sample.name, label: '样例标注', metadata: [sample.title],
      url: sample.original, risk: sample.report.risk, report: sample.report.json_report, action
    });
    if (explicit) this.revealDetail();
  }

  renderDetail({name, label, metadata, url, risk, report, action, recordId}) {
    this.source.textContent = label;
    const heading = this.node('h3', name, 'farm-record-heading');
    const meta = this.node('p', metadata.filter(Boolean).join(' · '), 'farm-record-meta');
    const media = this.node('div', null, 'farm-record-image');
    const actions = this.node('div', null, 'farm-record-actions');
    if (url) {
      const img = this.node('img');
      img.alt = name + ' 评估原图';
      const toggle = this.button('收起原图', () => {
        media.hidden = !media.hidden;
        toggle.textContent = media.hidden ? '查看原图' : '收起原图';
        toggle.setAttribute('aria-expanded', String(!media.hidden));
      });
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-controls', 'farm-original');
      media.id = 'farm-original';
      actions.append(toggle);
      img.addEventListener('error', () => {
        toggle.replaceWith(this.node('small', '本条记录的原图暂不可用'));
        media.replaceChildren();
      }, {once: true});
      img.src = url;
      media.append(img);
    } else {
      actions.append(this.node('small', '未留存原图'));
    }
    const badges = this.node('div', null, 'farm-record-badges');
    renderInspectionSummary(badges, risk);
    if (action) actions.append(action);
    const tools = this.node('div');
    renderReportTools(tools, report, recordId);
    const sections = this.node('div', null, 'farm-record-sections');
    if (report && typeof report === 'object' && Object.keys(report).length) renderInspectionReport(sections, report);
    else if (typeof report === 'string' && report.trim()) renderInspectionReport(sections, {'存档报告':report});
    else sections.textContent = '此记录仅保存了评估摘要。';
    this.detail.replaceChildren(heading, meta, badges, actions, media, tools, sections);
  }
}
