const form = document.getElementById('analysis-form');
const statusEl = document.getElementById('status');
const resultBox = document.getElementById('result-box');
const submitBtn = document.getElementById('submit-btn');
const modeIndicator = document.getElementById('mode-indicator');

async function loadExecutionMode() {
  try {
    const response = await fetch('/health');
    const data = await response.json();
    const mode = data.execution_mode || 'local_fallback';
    const label = mode === 'live_celesto'
      ? 'Live Celesto mode'
      : 'Local fallback mode';

    modeIndicator.textContent = label;
    modeIndicator.classList.toggle('live', mode === 'live_celesto');
    modeIndicator.classList.toggle('fallback', mode !== 'live_celesto');
  } catch (error) {
    modeIndicator.textContent = 'Mode unavailable';
    modeIndicator.classList.add('fallback');
  }
}

function renderStatus(text, error = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle('error', error);
}

function safeText(value, fallback = 'n/a') {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

function renderResult(payload) {
  const summary = payload.summary || payload;
  const status = safeText(payload.status || summary.status || 'complete');
  const runId = safeText(payload.run_id || 'n/a');
  const sandbox = safeText(payload.sandbox_name || 'n/a');
  const rows = safeText(summary.rows ?? 0);
  const columns = Array.isArray(summary.columns) ? summary.columns.join(', ') : 'n/a';
  const prompt = safeText(summary.prompt || 'No prompt supplied');
  const aiAnswer = safeText(summary.ai_answer || 'No detailed answer available.');
  const dtypes = summary.dtypes && Object.keys(summary.dtypes).length
    ? Object.entries(summary.dtypes).map(([key, value]) => `${key}: ${value}`).join(', ')
    : 'n/a';
  const nullCounts = summary.null_counts && Object.keys(summary.null_counts).length
    ? Object.entries(summary.null_counts).map(([key, value]) => `${key}: ${value}`).join(', ')
    : 'n/a';

  resultBox.classList.remove('empty');
  resultBox.innerHTML = `
    <div class="result-card">
      <div class="result-header">
        <span class="pill ${status === 'succeeded' ? '' : 'warning'}">${status}</span>
        <span class="micro-pill">${sandbox}</span>
      </div>

      <div class="mini-grid">
        <div class="metric">
          <span class="metric-label">Run ID</span>
          <span class="metric-value">${runId}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Rows</span>
          <span class="metric-value">${rows}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Columns</span>
          <span class="metric-value">${columns}</span>
        </div>
        <div class="metric">
          <span class="metric-label">Dtypes</span>
          <span class="metric-value">${dtypes}</span>
        </div>
      </div>

      <div class="answer-box">
        <strong>AI summary</strong>
        ${aiAnswer}
      </div>

      <div class="answer-box">
        <strong>Prompt</strong>
        ${prompt}
      </div>

      <div class="answer-box">
        <strong>Null counts</strong>
        ${nullCounts}
      </div>

      <div class="raw-box">
        <strong>Raw result</strong>
        <pre>${JSON.stringify(summary, null, 2)}</pre>
      </div>
    </div>
  `;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const fileInput = document.getElementById('file');
  const promptInput = document.getElementById('prompt');
  const file = fileInput.files[0];

  if (!file) {
    renderStatus('Please choose a CSV file first.', true);
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('prompt', promptInput.value || '');

  submitBtn.disabled = true;
  submitBtn.textContent = 'Running...';
  renderStatus('Submitting file to the sandbox...');

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      body: formData,
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || 'Request failed');
    }

    renderStatus(`Run complete: ${payload.run_id}`);
    renderResult(payload);
  } catch (error) {
    renderStatus(error.message || 'Something went wrong.', true);
    resultBox.classList.add('empty');
    resultBox.textContent = 'Unable to generate a result.';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Run analysis';
  }
});
