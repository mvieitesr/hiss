/**
 * Hiss Single Page Application
 * Pure vanilla JavaScript communicating with the Flask REST API (/api/v1).
 */

const API_BASE = '/api/v1';
const STATUS_VALUES = ['open', 'in_progress', 'done'];
const PRIORITY_VALUES = ['high', 'medium', 'low'];

const state = {
  projects: [],
  currentProject: null,
  currentProjectIssues: [],
  currentIssue: null,
  currentComments: [],
  allLabels: [],
  filters: {
    status: '',
    priority: '',
    label: ''
  },
  editingTitle: false,
  editingDescription: false,
  editingCommentId: null,
  appVersion: '...',
  issueRequestId: 0,
  navigationEpoch: 0,
  navigationHash: ''
};

// --- Small inline icon set -------------------------------------------------
// Keeping icons here avoids a runtime dependency while retaining a crisp,
// consistent visual language across the table and detail view.
const ICON_PATHS = {
  plus: '<path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  arrowRight: '<path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
  arrowUp: '<path d="M8 12.5V3.5M4.5 7 8 3.5 11.5 7" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/>',
  arrowDown: '<path d="M8 3.5v9M4.5 9 8 12.5 11.5 9" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/>',
  arrowUpRight: '<path d="M4 12 12 4M6 4h6v6" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
  circle: '<circle cx="8" cy="8" r="4.8" fill="none" stroke="currentColor" stroke-width="1.35"/>',
  clock: '<circle cx="8" cy="8" r="5.25" fill="none" stroke="currentColor" stroke-width="1.35"/><path d="M8 5v3.35l2.15 1.25" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>',
  check: '<path d="m3.4 8.1 2.8 2.8 6.4-6.2" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>',
  filter: '<path d="M2.75 3.5h10.5L9.2 7.85v3.4l-2.4 1.25V7.85L2.75 3.5Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>',
  tag: '<path d="M2.75 4.25V8l5.15 5.15a1.2 1.2 0 0 0 1.7 0l2.55-2.55a1.2 1.2 0 0 0 0-1.7L7 3.75H3.25a.5.5 0 0 0-.5.5Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><circle cx="5.15" cy="6.05" r=".75" fill="currentColor"/>',
  calendar: '<rect x="2.75" y="3.5" width="10.5" height="9.25" rx="1.25" fill="none" stroke="currentColor" stroke-width="1.25"/><path d="M5.25 2.5v2M10.75 2.5v2M2.75 6h10.5" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/>',
  message: '<path d="M3 3.25h10v7.2a1.3 1.3 0 0 1-1.3 1.3H7l-2.7 1.9v-1.9H4.3A1.3 1.3 0 0 1 3 10.45v-7.2Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>',
  project: '<path d="M2.75 4.25a1 1 0 0 1 1-1h3l1 1h4.5a1 1 0 0 1 1 1v6.5a1 1 0 0 1-1 1h-8.5a1 1 0 0 1-1-1v-7.5Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>',
  layers: '<path d="m8 2.5 5.5 2.85L8 8.2 2.5 5.35 8 2.5Z" fill="currentColor"/><path d="m2.5 8 5.5 2.85L13.5 8v2.35L8 13.2l-5.5-2.85V8Z" fill="currentColor" opacity=".62"/>',
  hash: '<path d="M5.25 2.75 4.5 13.25M10.75 2.75 10 13.25M2.75 6.2h10.5M2.25 9.8h10.5" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round"/>',
  x: '<path d="m4.5 4.5 7 7M11.5 4.5l-7 7" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round"/>',
  refresh: '<path d="M12.2 5.9A4.7 4.7 0 1 0 12.45 9" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/><path d="M12.25 3.7v2.65H9.6" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/>',
  inbox: '<path d="M3 4.25h10l.75 7a1 1 0 0 1-1 1.1H3.25a1 1 0 0 1-1-1.1l.75-7Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M2.25 8.5h2.6l.9 1.25h4.5l.9-1.25h2.6" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>',
  alert: '<path d="M8 2.5 13.25 12H2.75L8 2.5Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M8 6v2.75M8 10.45v.1" stroke="currentColor" stroke-width="1.45" stroke-linecap="round"/>',
  external: '<path d="M8.75 3.25h4v4M12.5 3.5 7.75 8.25" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/><path d="M11.25 8.5v3a1.25 1.25 0 0 1-1.25 1.25h-5a1.25 1.25 0 0 1-1.25-1.25v-5a1.25 1.25 0 0 1 1.25-1.25h3" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/>',
  dots: '<circle cx="3.5" cy="8" r=".9" fill="currentColor"/><circle cx="8" cy="8" r=".9" fill="currentColor"/><circle cx="12.5" cy="8" r=".9" fill="currentColor"/>',
  info: '<circle cx="8" cy="8" r="5.3" fill="none" stroke="currentColor" stroke-width="1.25"/><path d="M8 7.1v3.35M8 5.25v.1" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>',
  back: '<path d="M12.25 8H3.75M7.25 4.5 3.75 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
  search: '<circle cx="7" cy="7" r="3.7" fill="none" stroke="currentColor" stroke-width="1.25"/><path d="m9.75 9.75 3 3" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>',
  flame: '<path d="M8.45 13.25c2.25-.2 3.7-1.58 3.7-3.7 0-1.72-.98-3.05-2.35-4.2.12 1.3-.37 2.03-1.08 2.52.12-2.18-.9-3.7-2.2-5.12.08 2.35-2.65 3.18-2.65 6.15 0 2.43 1.87 4.25 4.58 4.35Z" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linejoin="round"/>',
  trash: '<path d="M3.5 4.5h9M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5m1.5 0v8a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 4.5 12.5v-8" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/>',
  edit: '<path d="m3 10.9-.45 2.55L5.1 13l7.1-7.1-2.1-2.1L3 10.9Z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="m9.3 4.5 2.1 2.1" fill="none" stroke="currentColor" stroke-width="1.2"/>',
  plusCircle: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 5v6M5 8h6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>',
  checkCircle: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="m5.25 8.1 1.75 1.75 3.75-3.7" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>'
};

function icon(name, className = 'icon', title = '') {
  const content = ICON_PATHS[name] || ICON_PATHS.circle;
  const titleMarkup = title ? `<title>${escapeHtml(title)}</title>` : '';
  return `<svg class="${className}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" aria-hidden="${title ? 'false' : 'true'}"${title ? '' : ' focusable="false"'}>${titleMarkup}${content}</svg>`;
}

// --- Helper utilities ------------------------------------------------------

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatDate(value, withTime = false) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  const options = withTime
    ? { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { month: 'short', day: 'numeric', year: 'numeric' };
  return date.toLocaleString(undefined, options);
}

function formatStatus(status) {
  const value = STATUS_VALUES.includes(status) ? status : 'open';
  if (value === 'in_progress') return 'In progress';
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatPriority(priority) {
  const value = ['low', 'medium', 'high'].includes(priority) ? priority : 'medium';
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function statusIcon(status) {
  if (status === 'done') return icon('check', 'icon icon-xs');
  if (status === 'in_progress') return icon('clock', 'icon icon-xs');
  return icon('circle', 'icon icon-xs');
}

function priorityIcon(priority) {
  if (priority === 'high') return icon('arrowUp', 'icon icon-xs');
  if (priority === 'low') return icon('arrowDown', 'icon icon-xs');
  return icon('arrowRight', 'icon icon-xs');
}

function labelTone(label) {
  const name = typeof label === 'string' ? label : (label && label.name) || '';
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
  return Math.abs(hash) % 6;
}

function showAlert(message, type = 'danger', dismissible = true) {
  const container = document.getElementById('alertContainer');
  if (!container) return;
  const safeType = ['success', 'info', 'warning', 'danger'].includes(type) ? type : 'danger';
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${safeType} alert-dismissible fade show`;
  alertDiv.setAttribute('role', 'alert');
  alertDiv.innerHTML = `<span>${escapeHtml(message)}</span>${dismissible ? '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Dismiss"></button>' : ''}`;
  container.appendChild(alertDiv);

  if (safeType !== 'danger') {
    window.setTimeout(() => {
      try {
        const alert = bootstrap.Alert.getOrCreateInstance(alertDiv);
        alert.close();
      } catch (error) {
        if (alertDiv.parentNode) alertDiv.remove();
      }
    }, 6000);
  }
}

function clearAlerts() {
  const container = document.getElementById('alertContainer');
  if (container) container.innerHTML = '';
}

async function apiRequest(url, options = {}) {
  const requestOptions = { ...options };
  const headers = {
    Accept: 'application/json',
    ...(options.headers || {})
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    requestOptions.body = JSON.stringify(options.body);
  }
  requestOptions.headers = headers;

  const response = await fetch(url, requestOptions);
  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) data = await response.json();

  if (!response.ok) {
    const error = new Error(data && data.message ? data.message : `Request failed with status ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function renderStatusBadge(status) {
  const value = STATUS_VALUES.includes(status) ? status : 'open';
  return `<span class="status-badge status-${value}">${statusIcon(value)}<span>${escapeHtml(formatStatus(value))}</span></span>`;
}

function renderPriorityBadge(priority) {
  const value = ['low', 'medium', 'high'].includes(priority) ? priority : 'medium';
  return `<span class="priority-badge priority-${value}">${priorityIcon(value)}<span>${escapeHtml(formatPriority(value))}</span></span>`;
}

function renderLabelBadge(label, removable = false, issueId = null, isCatalog = false) {
  const name = label && label.name ? String(label.name) : '';
  if (!name) return '';
  const tone = labelTone(name);
  let removeButton = '';
  if (isCatalog) {
    removeButton = `<button type="button" class="btn-close-custom" data-label-name="${escapeHtml(name)}" aria-label="Delete catalog label ${escapeHtml(name)}" onclick="app.handleDeleteCatalogLabel(this.dataset.labelName, event)">&times;</button>`;
  } else if (removable && issueId !== null) {
    removeButton = `<button type="button" class="btn-close-custom" data-label-name="${escapeHtml(name)}" aria-label="Remove ${escapeHtml(name)}" onclick="app.handleDetachLabel(${issueId}, this.dataset.labelName, event)">&times;</button>`;
  }
  return `<span class="label-pill label-tone-${tone}"><span>${escapeHtml(name)}</span>${removeButton}</span>`;
}

function renderErrorState(title, copy, actionMarkup = '') {
  const main = document.getElementById('mainContainer');
  if (!main) return;
  main.innerHTML = `
    <div class="empty-state">
      <div class="empty-state-icon">${icon('alert', 'icon')}</div>
      <h1 class="empty-state-title">${escapeHtml(title)}</h1>
      <p class="empty-state-copy">${escapeHtml(copy)}</p>
      ${actionMarkup}
    </div>
  `;
}

function renderFilterSelect(id, label, options, value) {
  const selectedClass = value ? ' has-value' : '';
  const optionsMarkup = options.map(option => `
    <option value="${escapeHtml(option.value)}" ${option.value === value ? 'selected' : ''}>${escapeHtml(option.label)}</option>
  `).join('');
  return `
    <div class="filter-field">
      <label class="filter-field-label" for="${id}">${escapeHtml(label)}</label>
      <select class="form-select form-select-sm filter-select${selectedClass}" id="${id}" aria-label="${escapeHtml(label)}" onchange="app.handleFilterChange()">${optionsMarkup}</select>
    </div>
  `;
}

// --- Routing ---------------------------------------------------------------

function parseHash() {
  const hash = window.location.hash.replace(/^#/, '');
  const parts = hash.split('/').filter(Boolean);
  if (parts.length === 0) return { view: 'projects' };
  if (parts[0] === 'projects') {
    return parts.length >= 2 ? { view: 'project_issues', key: decodeURIComponent(parts[1]) } : { view: 'projects' };
  }
  if (parts[0] === 'issues' && parts.length >= 2) {
    const id = Number.parseInt(parts[1], 10);
    return Number.isNaN(id) ? { view: 'projects' } : { view: 'issue_detail', id };
  }
  return { view: 'projects' };
}

function isCurrentNavigation(epoch) {
  return epoch === state.navigationEpoch && window.location.hash === state.navigationHash;
}

function isCurrentIssue(issueId, epoch) {
  const route = parseHash();
  return isCurrentNavigation(epoch) && route.view === 'issue_detail' && route.id === issueId;
}

function isCurrentProject(projectKey, epoch) {
  const route = parseHash();
  return isCurrentNavigation(epoch) && route.view === 'project_issues' && route.key === projectKey;
}

async function handleHashChange() {
  const epoch = ++state.navigationEpoch;
  state.navigationHash = window.location.hash;
  clearAlerts();
  state.editingTitle = false;
  state.editingDescription = false;
  state.editingCommentId = null;
  const main = document.getElementById('mainContainer');
  if (main) main.innerHTML = '<div class="loading-state" aria-label="Loading">Loading…</div>';
  const route = parseHash();
  if (route.view === 'projects') {
    await loadProjectsView(epoch);
  } else if (route.view === 'project_issues') {
    await loadProjectIssuesView(route.key, epoch);
  } else if (route.view === 'issue_detail') {
    await loadIssueDetailView(route.id, epoch);
  }
}

// --- Projects view ---------------------------------------------------------

async function loadProjectsView(epoch = state.navigationEpoch) {
  if (!isCurrentNavigation(epoch) || parseHash().view !== 'projects') return;
  state.currentProject = null;
  state.currentIssue = null;
  try {
    const projects = await apiRequest(`${API_BASE}/projects`);
    if (!isCurrentNavigation(epoch)) return;
    state.projects = projects || [];
    renderProjectsList(state.projects);
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || 'Failed to load projects');
    renderErrorState('Could not load projects', 'Check the API connection and try again.', '<button type="button" class="btn btn-sm btn-primary" onclick="app.retryProjects()">Try again</button>');
  }
}

function retryProjects() {
  clearAlerts();
  return loadProjectsView();
}

function renderProjectsList(projects) {
  const main = document.getElementById('mainContainer');
  if (!main) return;

  let content = `
    <div class="projects-container">
      <section class="page-header">
        <div>
          <div class="page-eyebrow">Workspace</div>
          <h1 class="page-title">Projects</h1>
          <p class="page-subtitle">Keep product work organized in focused project spaces.</p>
        </div>
        <button class="btn btn-sm btn-primary px-3" type="button" onclick="app.openCreateProjectModal()">
          ${icon('plus', 'icon icon-sm me-1')} New project
        </button>
      </section>
  `;

  if (!projects || projects.length === 0) {
    content += `
      <section class="empty-state">
        <div class="empty-state-icon">${icon('project', 'icon')}</div>
        <h2 class="empty-state-title">No projects yet</h2>
        <p class="empty-state-copy">Create a project to give your next set of issues a home.</p>
        <button class="btn btn-sm btn-primary px-3" type="button" onclick="app.openCreateProjectModal()">Create project</button>
      </section>
    `;
  } else {
    content += `<section class="project-list surface-card" aria-label="Projects">`;
    projects.forEach(project => {
      const openCount = typeof project.open_issues === 'number' ? project.open_issues : 0;
      const issueLabel = openCount === 1 ? 'open issue' : 'open issues';
      content += `
        <a class="project-list-row" href="#/projects/${encodeURIComponent(project.key)}">
          <div class="project-list-main">
            <span class="project-list-name">${escapeHtml(project.name)}</span>
            <span class="project-list-key">${escapeHtml(project.key)}</span>
          </div>
          <div class="project-list-meta">
            <span class="project-open-badge">${openCount} ${issueLabel}</span>
            <button type="button" class="btn-row-action" title="Delete project" aria-label="Delete project ${escapeHtml(project.key)}" data-project-key="${escapeHtml(project.key)}" onclick="app.handleDeleteProject(this.dataset.projectKey, event)">
              ${icon('trash', 'icon icon-xs')}
            </button>
          </div>
        </a>
      `;
    });
    content += '</section>';
  }
  content += `</div>`;
  main.innerHTML = content;
}

// --- Project issues view ---------------------------------------------------

async function loadProjectIssuesView(projectKey, epoch = state.navigationEpoch) {
  if (!isCurrentProject(projectKey, epoch)) return;
  if (!state.currentProject || state.currentProject.key !== projectKey) state.currentProjectIssues = [];
  try {
    const projects = await apiRequest(`${API_BASE}/projects`);
    if (!isCurrentNavigation(epoch)) return;
    state.projects = projects || [];
    const project = state.projects.find(item => item.key === projectKey);
    if (!project) {
      state.currentProject = null;
      showAlert(`Project '${projectKey}' not found.`);
      renderErrorState('Project not found', `There is no project named '${projectKey}'.`, '<a class="btn btn-sm btn-primary" href="#/projects">Back to projects</a>');
      return;
    }

    const projectChanged = !state.currentProject || state.currentProject.key !== project.key;
    state.currentProject = project;
    state.currentIssue = null;
    if (projectChanged) state.filters = { status: '', priority: '', label: '' };

    // Labels are used to populate the compact label filter. A label request
    // failure should not prevent the issue table from rendering.
    try {
      const labels = await apiRequest(`${API_BASE}/labels`);
      if (!isCurrentNavigation(epoch)) return;
      state.allLabels = labels || [];
    } catch (labelError) {
      if (!isCurrentNavigation(epoch)) return;
      state.allLabels = state.allLabels || [];
    }

    await fetchAndRenderIssues(epoch);
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || `Failed to load project '${projectKey}'`);
    renderErrorState('Could not load this project', 'Check the API connection and try again.', '<a class="btn btn-sm btn-light border" href="#/projects">Back to projects</a>');
  }
}

async function fetchAndRenderIssues(epoch = state.navigationEpoch) {
  if (!state.currentProject || !isCurrentProject(state.currentProject.key, epoch)) return;
  const projectKey = state.currentProject.key;
  const requestId = ++state.issueRequestId;
  const params = new URLSearchParams();
  if (state.filters.status) params.append('status', state.filters.status);
  if (state.filters.priority) params.append('priority', state.filters.priority);
  if (state.filters.label) params.append('label', state.filters.label);
  const query = params.toString() ? `?${params.toString()}` : '';

  try {
    const issues = await apiRequest(`${API_BASE}/projects/${encodeURIComponent(projectKey)}/issues${query}`);
    if (!isCurrentNavigation(epoch) || requestId !== state.issueRequestId) return;
    state.currentProjectIssues = issues || [];
    renderProjectIssuesView();
  } catch (error) {
    if (!isCurrentNavigation(epoch) || requestId !== state.issueRequestId) return;
    if (error.data && error.data.error === 'feature_disabled' && state.filters.label) {
      state.filters.label = '';
      state.currentProjectIssues = [];
      showAlert(error.message || 'Label filtering is not available in this environment.', 'warning');
      const main = document.getElementById('mainContainer');
      if (main) main.innerHTML = '<div class="loading-state" aria-label="Loading">Loading…</div>';
      await fetchAndRenderIssues(epoch);
      return;
    }
    state.currentProjectIssues = [];
    showAlert(error.message || 'Failed to fetch issues');
    renderErrorState('Could not load issues', 'Check the API connection and try again.', '<a class="btn btn-sm btn-light border" href="#/projects">Back to projects</a>');
  }
}

function renderProjectIssuesView() {
  const main = document.getElementById('mainContainer');
  const project = state.currentProject;
  if (!main || !project) return;

  const issues = state.currentProjectIssues || [];
  const activeIssues = issues.filter(issue => issue.status !== 'done').length;
  const statusOptions = [
    { value: '', label: 'All statuses' },
    { value: 'open', label: 'Open' },
    { value: 'in_progress', label: 'In progress' },
    { value: 'done', label: 'Done' }
  ];
  const priorityOptions = [
    { value: '', label: 'All priorities' },
    { value: 'high', label: 'High' },
    { value: 'medium', label: 'Medium' },
    { value: 'low', label: 'Low' }
  ];
  const labelOptions = [{ value: '', label: 'All labels' }];
  (state.allLabels || []).forEach(label => labelOptions.push({ value: label.name, label: label.name }));
  if (state.filters.label && !labelOptions.some(option => option.value === state.filters.label)) {
    labelOptions.push({ value: state.filters.label, label: state.filters.label });
  }
  const hasFilters = Boolean(state.filters.status || state.filters.priority || state.filters.label);
  const projectInitials = String(project.key || project.name || '?').slice(0, 2).toUpperCase();

  // Active filter pills
  const activePills = [];
  if (state.filters.status) {
    const opt = statusOptions.find(o => o.value === state.filters.status);
    const label = opt ? opt.label : state.filters.status;
    activePills.push(`
      <span class="filter-pill">
        <span class="filter-pill-label">Status:</span>
        <span class="filter-pill-value">${escapeHtml(label)}</span>
        <button type="button" class="filter-pill-remove" aria-label="Remove status filter" onclick="app.clearSingleFilter('status', event)">&times;</button>
      </span>
    `);
  }
  if (state.filters.priority) {
    const opt = priorityOptions.find(o => o.value === state.filters.priority);
    const label = opt ? opt.label : state.filters.priority;
    activePills.push(`
      <span class="filter-pill">
        <span class="filter-pill-label">Priority:</span>
        <span class="filter-pill-value">${escapeHtml(label)}</span>
        <button type="button" class="filter-pill-remove" aria-label="Remove priority filter" onclick="app.clearSingleFilter('priority', event)">&times;</button>
      </span>
    `);
  }
  if (state.filters.label) {
    activePills.push(`
      <span class="filter-pill">
        <span class="filter-pill-label">Label:</span>
        <span class="filter-pill-value">${escapeHtml(state.filters.label)}</span>
        <button type="button" class="filter-pill-remove" aria-label="Remove label filter" onclick="app.clearSingleFilter('label', event)">&times;</button>
      </span>
    `);
  }

  let content = `
    <div class="breadcrumb-row">
      <a href="#/projects">Projects</a>
      <span aria-hidden="true">/</span>
      <span class="breadcrumb-current">${escapeHtml(project.key)}</span>
    </div>
    <section class="project-heading">
      <div class="project-heading-main">
        <span class="project-avatar" aria-hidden="true">${escapeHtml(projectInitials)}</span>
        <div class="min-w-0">
          <h1 class="project-heading-title">${escapeHtml(project.name)}</h1>
          <div class="project-heading-meta">
            <span class="project-key-inline">${escapeHtml(project.key)}</span>
            <span aria-hidden="true">·</span>
            <span>${issues.length} ${issues.length === 1 ? 'issue' : 'issues'}</span>
            <span aria-hidden="true">·</span>
            <span>${activeIssues} active</span>
          </div>
        </div>
      </div>
      <button class="btn btn-sm btn-primary px-3" type="button" data-project-key="${escapeHtml(project.key)}" onclick="app.openCreateIssueModal(this.dataset.projectKey)">
        ${icon('plus', 'icon icon-sm me-1')} New issue
      </button>
    </section>

    <section class="issues-surface" aria-label="Issues">
      <div class="issues-table-control-bar">
        <div class="table-control-left">
          <div class="filter-pills-list">
            ${activePills.join('')}
            ${hasFilters ? `<button type="button" class="filter-clear-all-link" onclick="app.resetFilters()">Clear all</button>` : ''}
          </div>
        </div>
        <div class="table-control-right">
          <div class="dropdown filter-dropdown">
            <button class="btn btn-sm filter-toggle-btn${hasFilters ? ' has-filters' : ''}" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false">
              ${icon('filter', 'icon icon-xs me-1')} Filter
            </button>
            <div class="dropdown-menu dropdown-menu-end filter-popover p-3 shadow">
              <div class="filter-popover-header mb-2 pb-1 border-bottom d-flex justify-content-between align-items-center">
                <span class="fw-semibold small">Filter issues</span>
                ${hasFilters ? `<button type="button" class="btn btn-link btn-sm p-0 text-decoration-none small text-danger" onclick="app.resetFilters()">Clear all</button>` : ''}
              </div>
              <div class="filter-fields-stack">
                ${renderFilterSelect('filterStatus', 'Status', statusOptions, state.filters.status)}
                ${renderFilterSelect('filterPriority', 'Priority', priorityOptions, state.filters.priority)}
                ${renderFilterSelect('filterLabel', 'Label', labelOptions, state.filters.label)}
              </div>
            </div>
          </div>
          <span class="table-count-summary">${issues.length} ${issues.length === 1 ? 'issue' : 'issues'}${hasFilters ? ' matching' : ''}</span>
        </div>
      </div>

      <div class="issue-table-header" role="row">
        <span>Issue</span>
        <span>Status</span>
        <span>Priority</span>
        <span>Labels</span>
        <span class="align-right">Created</span>
      </div>
  `;

  if (issues.length === 0) {
    const copy = hasFilters ? 'Try clearing a filter or create an issue that matches your view.' : 'Create the first issue in this project to start tracking work.';
    content += `
      <div class="issue-list-empty">
        <div class="empty-state-icon">${icon(hasFilters ? 'search' : 'inbox', 'icon')}</div>
        <h3>${hasFilters ? 'No matching issues' : 'No issues yet'}</h3>
        <p>${escapeHtml(copy)}</p>
        ${hasFilters ? '<button type="button" class="btn btn-sm btn-light border me-1" onclick="app.resetFilters()">Clear filters</button>' : ''}
        <button type="button" class="btn btn-sm btn-primary" data-project-key="${escapeHtml(project.key)}" onclick="app.openCreateIssueModal(this.dataset.projectKey)">Create issue</button>
      </div>
    `;
  } else {
    content += renderIssueGroups(issues);
  }

  content += '</section>';
  main.innerHTML = content;
}

function renderIssueGroups(issues) {
  const groups = [];
  PRIORITY_VALUES.forEach(priority => {
    const matching = issues.filter(issue => issue.priority === priority);
    if (matching.length) groups.push({ priority, issues: matching });
  });
  const other = issues.filter(issue => !['high', 'medium', 'low'].includes(issue.priority));
  if (other.length) groups.push({ priority: 'medium', issues: other });

  return groups.map(group => `
    <div class="issue-group">
      <div class="issue-group-heading">
        ${priorityIcon(group.priority)}
        <span>${escapeHtml(formatPriority(group.priority))} priority</span>
        <span class="group-count">${group.issues.length}</span>
        <span class="group-spacer"></span>
      </div>
      ${group.issues.map(renderIssueRow).join('')}
    </div>
  `).join('');
}

function renderIssueRow(issue) {
  const status = STATUS_VALUES.includes(issue.status) ? issue.status : 'open';
  const priority = ['low', 'medium', 'high'].includes(issue.priority) ? issue.priority : 'medium';
  const labels = issue.labels || [];
  const visibleLabels = labels.slice(0, 3).map(label => renderLabelBadge(label)).join('');
  const moreLabels = labels.length > 3 ? `<span class="labels-more">+${labels.length - 3}</span>` : '';
  const labelMarkup = visibleLabels || '<span class="no-labels">—</span>';
  const createdAt = issue.created_at ? formatDate(issue.created_at) : 'Unknown';

  return `
    <a class="issue-row" href="#/issues/${escapeHtml(issue.id)}">
      <div class="issue-main-cell">
        <span class="issue-id-cell">#${escapeHtml(issue.id)}</span>
        <span class="issue-status-dot status-${status}" title="${escapeHtml(formatStatus(status))}">${statusIcon(status)}</span>
        <span class="issue-copy">
          <span class="issue-title">${escapeHtml(issue.title)}</span>
          ${issue.description ? `<span class="issue-description-preview">${escapeHtml(issue.description)}</span>` : ''}
        </span>
      </div>
      <div class="status-cell"><span class="mobile-cell-label">Status</span>${renderStatusBadge(status)}</div>
      <div class="priority-cell"><span class="mobile-cell-label">Priority</span>${renderPriorityBadge(priority)}</div>
      <div class="labels-cell"><span class="mobile-cell-label">Labels</span>${labelMarkup}${moreLabels}</div>
      <div class="created-cell"><span class="mobile-cell-label">Created</span><span title="${escapeHtml(issue.created_at || '')}">${escapeHtml(createdAt)}</span></div>
    </a>
  `;
}

// --- Issue detail view -----------------------------------------------------

async function loadIssueDetailView(issueId, epoch = state.navigationEpoch) {
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const issue = await apiRequest(`${API_BASE}/issues/${issueId}`);
    if (!isCurrentNavigation(epoch)) return;

    const [comments, labels] = await Promise.all([
      apiRequest(`${API_BASE}/issues/${issueId}/comments`),
      apiRequest(`${API_BASE}/labels`)
    ]);
    if (!isCurrentNavigation(epoch)) return;

    let projects = state.projects || [];
    let matchingProject = projects.find(project => project.id === issue.project_id);
    if (!matchingProject) {
      try {
        projects = await apiRequest(`${API_BASE}/projects`) || [];
        if (!isCurrentNavigation(epoch)) return;
        matchingProject = projects.find(project => project.id === issue.project_id);
      } catch (projectError) {
        if (!isCurrentNavigation(epoch)) return;
        matchingProject = null;
      }
    }
    state.currentIssue = issue;
    state.currentComments = comments || [];
    state.allLabels = labels || [];
    state.projects = projects;
    state.currentProject = matchingProject || null;
    state.editingTitle = false;
    state.editingDescription = false;
    state.editingCommentId = null;
    renderIssueDetailView();
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || `Failed to load issue #${issueId}`);
    renderErrorState('Could not load this issue', 'The issue may have been removed or the API is unavailable.', '<a class="btn btn-sm btn-light border" href="#/projects">Back to projects</a>');
  }
}

function renderIssueDetailView() {
  const main = document.getElementById('mainContainer');
  const issue = state.currentIssue;
  if (!main || !issue) return;

  const comments = state.currentComments || [];
  const allLabels = state.allLabels || [];
  const project = state.currentProject;
  const projectKey = project ? project.key : `Project #${issue.project_id}`;
  const attachedLabels = issue.labels || [];
  const attachedNames = new Set(attachedLabels.map(label => label.name));
  const availableLabels = allLabels.filter(label => !attachedNames.has(label.name));
  const detailBackHref = project ? `#/projects/${encodeURIComponent(project.key)}` : '#/projects';
  const created = issue.created_at ? formatDate(issue.created_at, true) : 'Unknown';

  let content = `
    <div class="breadcrumb-row detail-breadcrumb">
      <a href="#/projects">Projects</a>
      <span aria-hidden="true">/</span>
      <a href="${detailBackHref}">${escapeHtml(projectKey)}</a>
      <span aria-hidden="true">/</span>
      <span class="breadcrumb-current">#${escapeHtml(issue.id)}</span>
    </div>

    <section class="detail-title-section">
      <div class="detail-eyebrow">
        <span class="detail-project-key">${escapeHtml(projectKey)}</span>
        <span aria-hidden="true">·</span>
        <span>Issue #${escapeHtml(issue.id)}</span>
      </div>
  `;

  if (state.editingTitle) {
    content += `
      <form class="detail-title-edit-form" onsubmit="app.handleSaveTitle(event, ${escapeHtml(issue.id)})">
        <input type="text" class="form-control form-control-app detail-title-input" id="editTitleInput" value="${escapeHtml(issue.title)}" required autofocus>
        <button type="submit" class="btn btn-sm btn-primary">Save</button>
        <button type="button" class="btn btn-sm btn-light border" onclick="app.cancelEditTitle()">Cancel</button>
      </form>
    `;
  } else {
    content += `
      <div class="detail-title-header">
        <div class="detail-title-display">
          <h1 class="detail-title">${escapeHtml(issue.title)}</h1>
          <span class="detail-issue-number">#${escapeHtml(issue.id)}</span>
        </div>
        <div class="detail-title-actions">
          <button type="button" class="btn btn-sm btn-light border" onclick="app.startEditTitle()">
            ${icon('edit', 'icon icon-xs me-1')} Edit
          </button>
        </div>
      </div>
    `;
  }

  content += `
      <div class="detail-title-meta">
        ${renderStatusBadge(issue.status)}
        ${renderPriorityBadge(issue.priority)}
        <span class="meta-separator" aria-hidden="true">·</span>
        <span title="${escapeHtml(issue.created_at || '')}">Created ${escapeHtml(created)}</span>
        <span class="meta-separator" aria-hidden="true">·</span>
        <span>${comments.length} ${comments.length === 1 ? 'comment' : 'comments'}</span>
      </div>
    </section>

    <div class="detail-layout">
      <div class="detail-timeline">
        <!-- Description timeline item -->
        <div class="timeline-item">
          <article class="timeline-box">
            <div class="timeline-header">
              <div class="timeline-header-left">
                <span class="timeline-author">Description</span>
                <span class="timeline-time">${escapeHtml(created)}</span>
              </div>
              <div class="timeline-actions">
                ${state.editingDescription ? '' : `
                  <button type="button" class="timeline-action-btn" onclick="app.startEditDescription()">
                    ${icon('edit', 'icon icon-xs me-1')} Edit
                  </button>
                `}
              </div>
            </div>
  `;

  if (state.editingDescription) {
    content += `
      <form class="timeline-edit-form" onsubmit="app.handleSaveDescription(event, ${escapeHtml(issue.id)})">
        <textarea class="form-control form-control-app" id="editDescriptionInput" rows="5" placeholder="Add a description…">${escapeHtml(issue.description || '')}</textarea>
        <div class="timeline-edit-actions">
          <button type="button" class="btn btn-sm btn-light border" onclick="app.cancelEditDescription()">Cancel</button>
          <button type="submit" class="btn btn-sm btn-primary px-3">Save</button>
        </div>
      </form>
    `;
  } else {
    content += `
      <div class="timeline-body${issue.description ? '' : ' timeline-body-empty'}">${escapeHtml(issue.description || 'No description provided.')}</div>
    `;
  }

  content += `
          </article>
        </div>

        <!-- Comments timeline items -->
  `;

  comments.forEach(comment => {
    const isEditing = state.editingCommentId === comment.id;
    const commentDate = comment.created_at ? formatDate(comment.created_at, true) : '';
    content += `
      <div class="timeline-item">
        <article class="timeline-box">
          <div class="timeline-header">
            <div class="timeline-header-left">
              <span class="timeline-author">Comment</span>
              <span class="timeline-badge">#${escapeHtml(comment.id)}</span>
              <span class="timeline-time">${escapeHtml(commentDate)}</span>
            </div>
            <div class="timeline-actions">
              ${isEditing ? '' : `
                <button type="button" class="timeline-action-btn" onclick="app.startEditComment(${escapeHtml(comment.id)})">
                  ${icon('edit', 'icon icon-xs me-1')} Edit
                </button>
                <button type="button" class="timeline-action-btn danger" onclick="app.handleDeleteComment(${escapeHtml(comment.id)}, ${escapeHtml(issue.id)})">
                  ${icon('trash', 'icon icon-xs me-1')} Delete
                </button>
              `}
            </div>
          </div>
    `;

    if (isEditing) {
      content += `
        <form class="timeline-edit-form" onsubmit="app.handleSaveComment(event, ${escapeHtml(comment.id)}, ${escapeHtml(issue.id)})">
          <textarea class="form-control form-control-app" id="editCommentInput_${escapeHtml(comment.id)}" rows="4" required>${escapeHtml(comment.body)}</textarea>
          <div class="timeline-edit-actions">
            <button type="button" class="btn btn-sm btn-light border" onclick="app.cancelEditComment()">Cancel</button>
            <button type="submit" class="btn btn-sm btn-primary px-3">Save</button>
          </div>
        </form>
      `;
    } else {
      content += `
        <div class="timeline-body">${escapeHtml(comment.body)}</div>
      `;
    }

    content += `
        </article>
      </div>
    `;
  });

  content += `
        <!-- Add comment composer -->
        <div class="composer-box">
          <div class="composer-header">Add a comment</div>
          <form class="composer-body" onsubmit="app.handleAddComment(event, ${escapeHtml(issue.id)})">
            <textarea class="form-control form-control-app" id="commentBodyInput" rows="3" placeholder="Leave a comment…" required></textarea>
            <div class="composer-footer">
              <span class="composer-hint">Comments are visible on this issue.</span>
              <button type="submit" class="btn btn-sm btn-primary px-3">Comment</button>
            </div>
          </form>
        </div>
      </div>

      <aside class="issue-sidebar" aria-label="Issue properties">
        <section class="surface-card properties-card">
          <div class="properties-heading"><span>Properties</span><span class="text-muted small">Editable</span></div>
          <div class="property-row">
            <label class="property-label" for="issueStatusSelect">${icon('circle', 'icon icon-sm')} Status</label>
            <select class="form-select form-select-sm property-select" id="issueStatusSelect" aria-label="Issue status" onchange="app.handleUpdateStatus(${escapeHtml(issue.id)}, this.value)">
              <option value="open" ${issue.status === 'open' ? 'selected' : ''}>Open</option>
              <option value="in_progress" ${issue.status === 'in_progress' ? 'selected' : ''}>In progress</option>
              <option value="done" ${issue.status === 'done' ? 'selected' : ''}>Done</option>
            </select>
          </div>
          <div class="property-row">
            <label class="property-label" for="issuePrioritySelectDetail">${icon('arrowUpRight', 'icon icon-sm')} Priority</label>
            <select class="form-select form-select-sm property-select" id="issuePrioritySelectDetail" aria-label="Issue priority" onchange="app.handleUpdatePriority(${escapeHtml(issue.id)}, this.value)">
              <option value="low" ${issue.priority === 'low' ? 'selected' : ''}>Low</option>
              <option value="medium" ${issue.priority === 'medium' ? 'selected' : ''}>Medium</option>
              <option value="high" ${issue.priority === 'high' ? 'selected' : ''}>High</option>
            </select>
          </div>
        </section>

        <section class="surface-card properties-card">
          <div class="properties-heading">
            <span>Labels</span>
            <button type="button" class="manage-labels-button" onclick="app.openManageLabelsModal(event)">Manage</button>
          </div>
          <div class="sidebar-labels">
            ${attachedLabels.length ? attachedLabels.map(label => renderLabelBadge(label, true, issue.id)).join('') : '<span class="no-attached-labels">No labels attached</span>'}
          </div>
          <div class="label-attach-row">
            <label class="visually-hidden" for="attachLabelSelect">Attach a label</label>
            <select class="form-select form-select-sm form-select-app" id="attachLabelSelect" aria-label="Attach a label" ${availableLabels.length ? '' : 'disabled'}>
              <option value="">${availableLabels.length ? 'Attach a label…' : 'No labels available'}</option>
              ${availableLabels.map(label => `<option value="${escapeHtml(label.name)}">${escapeHtml(label.name)}</option>`).join('')}
            </select>
            <button class="btn btn-sm btn-light border" type="button" onclick="app.handleAttachSelectedLabel(${escapeHtml(issue.id)})" ${availableLabels.length ? '' : 'disabled'}>Add</button>
          </div>
        </section>

        <section class="surface-card properties-card">
          <div class="properties-heading"><span>Details</span></div>
          <div class="property-row">
            <span class="property-label">${icon('project', 'icon icon-sm')} Project</span>
            <span class="property-value">${escapeHtml(projectKey)}</span>
          </div>
          <div class="property-row">
            <span class="property-label">${icon('hash', 'icon icon-sm')} Issue ID</span>
            <span class="property-value monospace">#${escapeHtml(issue.id)}</span>
          </div>
          <div class="property-row">
            <span class="property-label">${icon('calendar', 'icon icon-sm')} Created</span>
            <span class="property-value" title="${escapeHtml(issue.created_at || '')}">${escapeHtml(issue.created_at ? formatDate(issue.created_at) : 'Unknown')}</span>
          </div>
        </section>

        <section class="surface-card properties-card">
          <div class="properties-heading"><span class="text-danger">Danger zone</span></div>
          <div class="sidebar-danger-zone">
            <button type="button" class="btn btn-sm btn-ghost-danger w-100" onclick="app.handleDeleteIssue(${escapeHtml(issue.id)})">
              ${icon('trash', 'icon icon-xs me-1')} Delete issue
            </button>
          </div>
        </section>
      </aside>
    </div>
  `;

  main.innerHTML = content;
}

// --- Action handlers -------------------------------------------------------

async function handleCreateProject(event) {
  event.preventDefault();
  const keyInput = document.getElementById('projectKeyInput');
  const nameInput = document.getElementById('projectNameInput');
  if (!keyInput || !nameInput) return;

  const key = keyInput.value.trim().toUpperCase();
  const name = nameInput.value.trim();
  const epoch = state.navigationEpoch;
  try {
    await apiRequest(`${API_BASE}/projects`, { method: 'POST', body: { key, name } });
    if (!isCurrentNavigation(epoch)) return;
    const modal = bootstrap.Modal.getInstance(document.getElementById('createProjectModal'));
    if (modal) modal.hide();
    keyInput.value = '';
    nameInput.value = '';
    showAlert(`Project '${key}' created successfully.`, 'success');
    window.location.hash = `#/projects/${encodeURIComponent(key)}`;
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || 'Failed to create project');
  }
}

async function handleDeleteProject(projectKey, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  const confirmed = window.confirm(`Are you sure you want to delete project '${projectKey}' and all of its issues?`);
  if (!confirmed) return;

  const epoch = state.navigationEpoch;
  try {
    await apiRequest(`${API_BASE}/projects/${encodeURIComponent(projectKey)}`, { method: 'DELETE' });
    if (!isCurrentNavigation(epoch)) return;
    showAlert(`Project '${projectKey}' deleted.`, 'success');
    await loadProjectsView(epoch);
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || `Failed to delete project '${projectKey}'`);
  }
}

async function handleCreateIssue(event) {
  event.preventDefault();
  if (!state.currentProject) return;
  const titleInput = document.getElementById('issueTitleInput');
  const descriptionInput = document.getElementById('issueDescriptionInput');
  const prioritySelect = document.getElementById('issuePrioritySelect');
  if (!titleInput || !descriptionInput || !prioritySelect) return;

  const epoch = state.navigationEpoch;
  try {
    const newIssue = await apiRequest(`${API_BASE}/projects/${encodeURIComponent(state.currentProject.key)}/issues`, {
      method: 'POST',
      body: {
        title: titleInput.value.trim(),
        description: descriptionInput.value.trim(),
        priority: prioritySelect.value
      }
    });
    if (!isCurrentNavigation(epoch)) return;
    const modal = bootstrap.Modal.getInstance(document.getElementById('createIssueModal'));
    if (modal) modal.hide();
    titleInput.value = '';
    descriptionInput.value = '';
    prioritySelect.value = 'medium';
    showAlert(`Issue #${newIssue.id} created.`, 'success');
    window.location.hash = `#/issues/${newIssue.id}`;
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || 'Failed to create issue');
  }
}

async function handleDeleteIssue(issueId) {
  const confirmed = window.confirm(`Are you sure you want to delete issue #${issueId}?`);
  if (!confirmed) return;

  const projectKey = state.currentProject ? state.currentProject.key : null;
  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    await apiRequest(`${API_BASE}/issues/${issueId}`, { method: 'DELETE' });
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(`Issue #${issueId} deleted.`, 'success');
    if (projectKey) {
      window.location.hash = `#/projects/${encodeURIComponent(projectKey)}`;
    } else {
      window.location.hash = '#/projects';
    }
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || `Failed to delete issue #${issueId}`);
  }
}

function startEditTitle() {
  state.editingTitle = true;
  renderIssueDetailView();
  const input = document.getElementById('editTitleInput');
  if (input) {
    input.focus();
    input.select();
  }
}

function cancelEditTitle() {
  state.editingTitle = false;
  renderIssueDetailView();
}

async function handleSaveTitle(event, issueId) {
  event.preventDefault();
  const input = document.getElementById('editTitleInput');
  if (!input) return;
  const title = input.value.trim();
  if (!title) {
    showAlert('Title cannot be empty');
    return;
  }

  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const updated = await apiRequest(`${API_BASE}/issues/${issueId}`, { method: 'PATCH', body: { title } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentIssue = updated;
    state.editingTitle = false;
    renderIssueDetailView();
    showAlert('Title updated.', 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to update title');
  }
}

function startEditDescription() {
  state.editingDescription = true;
  renderIssueDetailView();
  const input = document.getElementById('editDescriptionInput');
  if (input) {
    input.focus();
  }
}

function cancelEditDescription() {
  state.editingDescription = false;
  renderIssueDetailView();
}

async function handleSaveDescription(event, issueId) {
  event.preventDefault();
  const input = document.getElementById('editDescriptionInput');
  if (!input) return;
  const description = input.value;

  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const updated = await apiRequest(`${API_BASE}/issues/${issueId}`, { method: 'PATCH', body: { description } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentIssue = updated;
    state.editingDescription = false;
    renderIssueDetailView();
    showAlert('Description updated.', 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to update description');
  }
}

function startEditComment(commentId) {
  state.editingCommentId = commentId;
  renderIssueDetailView();
  const input = document.getElementById(`editCommentInput_${commentId}`);
  if (input) {
    input.focus();
  }
}

function cancelEditComment() {
  state.editingCommentId = null;
  renderIssueDetailView();
}

async function handleSaveComment(event, commentId, issueId) {
  event.preventDefault();
  const input = document.getElementById(`editCommentInput_${commentId}`);
  if (!input) return;
  const body = input.value.trim();
  if (!body) {
    showAlert('Comment body cannot be empty');
    return;
  }

  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const updatedComment = await apiRequest(`${API_BASE}/comments/${commentId}`, { method: 'PATCH', body: { body } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentComments = (state.currentComments || []).map(c => c.id === commentId ? updatedComment : c);
    state.editingCommentId = null;
    renderIssueDetailView();
    showAlert('Comment updated.', 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to update comment');
  }
}

async function handleDeleteComment(commentId, issueId) {
  const confirmed = window.confirm(`Are you sure you want to delete comment #${commentId}?`);
  if (!confirmed) return;

  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    await apiRequest(`${API_BASE}/comments/${commentId}`, { method: 'DELETE' });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentComments = (state.currentComments || []).filter(c => c.id !== commentId);
    renderIssueDetailView();
    showAlert('Comment deleted.', 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to delete comment');
  }
}

async function handleUpdateStatus(issueId, newStatus) {
  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const updated = await apiRequest(`${API_BASE}/issues/${issueId}`, { method: 'PATCH', body: { status: newStatus } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentIssue = updated;
    renderIssueDetailView();
    showAlert(`Status updated to '${formatStatus(newStatus)}'.`, 'info');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to update status');
    await loadIssueDetailView(issueId, epoch);
  }
}

async function handleUpdatePriority(issueId, newPriority) {
  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const updated = await apiRequest(`${API_BASE}/issues/${issueId}`, { method: 'PATCH', body: { priority: newPriority } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentIssue = updated;
    renderIssueDetailView();
    showAlert(`Priority updated to '${formatPriority(newPriority)}'.`, 'info');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to update priority');
    await loadIssueDetailView(issueId, epoch);
  }
}

async function handleAddComment(event, issueId) {
  event.preventDefault();
  const input = document.getElementById('commentBodyInput');
  if (!input) return;
  const body = input.value.trim();
  if (!body) return;

  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const newComment = await apiRequest(`${API_BASE}/issues/${issueId}/comments`, { method: 'POST', body: { body } });
    if (!isCurrentIssue(issueId, epoch)) return;
    state.currentComments = [...(state.currentComments || []), newComment];
    renderIssueDetailView();
    showAlert('Comment added.', 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to add comment');
  }
}

async function handleAttachSelectedLabel(issueId) {
  const select = document.getElementById('attachLabelSelect');
  if (!select || !select.value) return;
  const labelName = select.value;
  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const attached = await apiRequest(`${API_BASE}/issues/${issueId}/labels/${encodeURIComponent(labelName)}`, { method: 'POST' });
    if (!isCurrentIssue(issueId, epoch)) return;
    if (state.currentIssue) {
      state.currentIssue.labels = attached.labels || [];
    }
    renderIssueDetailView();
    showAlert(`Label '${labelName}' attached.`, 'success');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to attach label');
  }
}

async function handleDetachLabel(issueId, labelName, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  const epoch = state.navigationEpoch;
  if (!isCurrentIssue(issueId, epoch)) return;
  try {
    const remaining = await apiRequest(`${API_BASE}/issues/${issueId}/labels/${encodeURIComponent(labelName)}`, { method: 'DELETE' });
    if (!isCurrentIssue(issueId, epoch)) return;
    if (state.currentIssue) {
      state.currentIssue.labels = remaining.labels || [];
    }
    renderIssueDetailView();
    showAlert(`Label '${labelName}' removed.`, 'info');
  } catch (error) {
    if (!isCurrentIssue(issueId, epoch)) return;
    showAlert(error.message || 'Failed to remove label');
  }
}

async function handleCreateLabel(event) {
  event.preventDefault();
  const input = document.getElementById('newLabelNameInput');
  if (!input) return;
  const name = input.value.trim();
  if (!name) return;

  const epoch = state.navigationEpoch;
  try {
    await apiRequest(`${API_BASE}/labels`, { method: 'POST', body: { name } });
    if (!isCurrentNavigation(epoch)) return;
    input.value = '';
    showAlert(`Label '${name}' created.`, 'success');
    await refreshManageLabelsModal(epoch);
    if (!isCurrentNavigation(epoch)) return;
    if (state.currentIssue) {
      await loadIssueDetailView(state.currentIssue.id, epoch);
    } else if (state.currentProject) {
      await fetchAndRenderIssues(epoch);
    }
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || 'Failed to create label');
  }
}

async function handleDeleteCatalogLabel(labelName, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  const confirmed = window.confirm(`Are you sure you want to delete label '${labelName}'? It will be removed from all issues.`);
  if (!confirmed) return;

  const epoch = state.navigationEpoch;
  try {
    await apiRequest(`${API_BASE}/labels/${encodeURIComponent(labelName)}`, { method: 'DELETE' });
    if (!isCurrentNavigation(epoch)) return;
    showAlert(`Label '${labelName}' deleted.`, 'info');
    await refreshManageLabelsModal(epoch);
    if (!isCurrentNavigation(epoch)) return;
    if (state.currentIssue) {
      await loadIssueDetailView(state.currentIssue.id, epoch);
    } else if (state.currentProject) {
      await fetchAndRenderIssues(epoch);
    }
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    showAlert(error.message || `Failed to delete label '${labelName}'`);
  }
}

async function refreshManageLabelsModal(epoch = state.navigationEpoch) {
  try {
    const labels = await apiRequest(`${API_BASE}/labels`);
    if (!isCurrentNavigation(epoch)) return;
    state.allLabels = labels || [];
    const container = document.getElementById('labelsListContainer');
    if (!container) return;
    container.innerHTML = state.allLabels.length
      ? state.allLabels.map(label => renderLabelBadge(label, true, null, true)).join('')
      : '<span class="empty-inline">No labels created yet.</span>';
  } catch (error) {
    if (!isCurrentNavigation(epoch)) return;
    const container = document.getElementById('labelsListContainer');
    if (container) container.innerHTML = '<span class="empty-inline">Labels could not be loaded.</span>';
  }
}

function handleFilterChange() {
  const status = document.getElementById('filterStatus');
  const priority = document.getElementById('filterPriority');
  const label = document.getElementById('filterLabel');
  state.filters.status = status ? status.value : '';
  state.filters.priority = priority ? priority.value : '';
  state.filters.label = label ? label.value : '';
  fetchAndRenderIssues();
}

function clearSingleFilter(filterKey, event) {
  if (event) event.stopPropagation();
  if (filterKey in state.filters) {
    state.filters[filterKey] = '';
    fetchAndRenderIssues();
  }
}

function resetFilters() {
  state.filters = { status: '', priority: '', label: '' };
  fetchAndRenderIssues();
}

// --- Modal helpers and navigation -----------------------------------------

function openCreateProjectModal() {
  const element = document.getElementById('createProjectModal');
  if (element) bootstrap.Modal.getOrCreateInstance(element).show();
}

function openCreateIssueModal(projectKey) {
  const keyElement = document.getElementById('createIssueProjectKey');
  if (keyElement) keyElement.textContent = projectKey || (state.currentProject && state.currentProject.key) || '';
  const element = document.getElementById('createIssueModal');
  if (element) bootstrap.Modal.getOrCreateInstance(element).show();
}

async function openManageLabelsModal(event) {
  if (event) event.preventDefault();
  const epoch = state.navigationEpoch;
  await refreshManageLabelsModal(epoch);
  if (!isCurrentNavigation(epoch)) return;
  const element = document.getElementById('manageLabelsModal');
  if (element) bootstrap.Modal.getOrCreateInstance(element).show();
}

function navigateHome(event) {
  if (event) event.preventDefault();
  window.location.hash = '#/projects';
}

// --- Initialization --------------------------------------------------------

async function fetchAppVersion() {
  try {
    const response = await fetch('/version');
    if (!response.ok) return;
    const data = await response.json();
    state.appVersion = data.version || 'dev';
    const badge = document.getElementById('appVersionBadge');
    if (badge) badge.textContent = `v${state.appVersion}`;
  } catch (error) {
    // The version badge is informational; the app remains usable if it fails.
  }
}

window.addEventListener('hashchange', handleHashChange);

document.addEventListener('DOMContentLoaded', () => {
  fetchAppVersion();
  if (!window.location.hash || window.location.hash === '#') {
    window.location.hash = '#/projects';
  } else {
    handleHashChange();
  }
});

window.app = {
  navigateHome,
  retryProjects,
  openCreateProjectModal,
  openCreateIssueModal,
  openManageLabelsModal,
  handleCreateProject,
  handleDeleteProject,
  handleCreateIssue,
  handleDeleteIssue,
  startEditTitle,
  cancelEditTitle,
  handleSaveTitle,
  startEditDescription,
  cancelEditDescription,
  handleSaveDescription,
  startEditComment,
  cancelEditComment,
  handleSaveComment,
  handleDeleteComment,
  handleCreateLabel,
  handleDeleteCatalogLabel,
  handleAddComment,
  handleUpdateStatus,
  handleUpdatePriority,
  handleAttachSelectedLabel,
  handleDetachLabel,
  handleFilterChange,
  clearSingleFilter,
  resetFilters
};
