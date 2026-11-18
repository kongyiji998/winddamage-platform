// Interpolate within the current image; each completed request advances the batch.
class InspectionProgress {
  constructor(bar, readout) {
    this.bar = bar;
    this.readout = readout;
    this.secondsPerImage = 12;
  }

  start(imageCount = 1) {
    this.reset();
    this.imageCount = imageCount;
    this.finished = 0;
    this.startedAt = this.imageStartedAt = performance.now();
    this.paint(0, 0);
    this.bar.hidden = this.readout.hidden = false;
    this.timer = window.setInterval(() => {
      const now = performance.now();
      const fraction = Math.min(0.98, 1 - Math.exp(-2 * (now - this.imageStartedAt) / 1000 / this.secondsPerImage));
      const estimated = Math.floor(100 * (this.finished + fraction) / this.imageCount);
      this.paint(Math.min(99, estimated), (now - this.startedAt) / 1000);
    }, 200);
  }

  imageFinished(count) {
    this.finished = count;
    this.imageStartedAt = performance.now();
    this.paint(Math.floor(100 * count / this.imageCount), (this.imageStartedAt - this.startedAt) / 1000);
  }

  paint(percent, seconds) {
    const label = (percent === 100 ? '已完成 ' : '预计进度 ') + percent + '%';
    this.bar.style.setProperty('--progress-fill', String(percent / 100));
    this.bar.setAttribute('aria-valuenow', String(percent));
    this.bar.setAttribute('aria-valuetext', label);
    this.readout.textContent = label + ' · 已用 ' + Math.floor(seconds) + ' 秒';
  }

  complete() {
    window.clearInterval(this.timer);
    const seconds = (performance.now() - this.startedAt) / 1000;
    this.secondsPerImage = Math.max(1, seconds / this.imageCount);
    this.paint(100, seconds);
  }

  reset() {
    window.clearInterval(this.timer);
    this.bar.hidden = this.readout.hidden = true;
    this.bar.style.removeProperty('--progress-fill');
    this.bar.removeAttribute('aria-valuenow');
    this.bar.removeAttribute('aria-valuetext');
    this.readout.textContent = '';
  }
}
