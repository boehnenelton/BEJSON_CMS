/*
File:          src/web/fb_assets/becss-filepicker.js
Description:   In-app file picker. Browses the device filesystem through the
               server (/fb/api/*) so the page NEVER leaves the foreground - the
               native OS file chooser is what got the CMS killed on Android.
               Returns absolute SERVER paths; import routes read them directly.

  JS API
    CMSFilePicker.open({kind, multiple, title, confirmLabel, subtitle})
        -> Promise<{paths:[...], files:[{path,name,size}]} | null>
    CMSFilePicker.postJSON(url, body) -> Promise<json>   (throws Error on failure)

  Declarative:  <button type="button" data-fb-pick data-fb-kind="html"
                  data-fb-multiple="1" data-fb-target="#hidden-input"
                  data-fb-summary="#list-div">Browse</button>
    -> fills #hidden-input with newline-separated paths, lists names in
       #list-div, and fires a bubbling 'fb:picked' CustomEvent (detail = result).

  kinds: image video audio document media html zip app code markdown keys any

Version:       18.29
Author:        Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
RELATIONAL_ID: 2f4b8c1e-6a3d-4d7f-9b25-c0e1a8d34f67
*/
(function () {
  'use strict';
  if (window.CMSFilePicker) { return; }

  var API = '/fb/api';
  var STORE_KEY = 'becss_filepicker_v1';
  var PAGE_SIZE = 200;
  var ICONS = {
    folder: '📁', image: '🖼️', video: '🎬', audio: '🎵',
    document: '📄', html: '🌐', zip: '🗜️', code: '💻',
    markdown: '📝', keys: '🔑', other: '📦'
  };
  var KIND_TITLES = {
    image: 'Select images', video: 'Select videos', audio: 'Select audio', document: 'Select PDFs',
    media: 'Select media files', html: 'Select HTML files', zip: 'Select a ZIP', app: 'Select an HTML file or ZIP',
    code: 'Select a code file', markdown: 'Select a Markdown file', keys: 'Select a key file', any: 'Select files'
  };

  function storeRead() {
    try { return JSON.parse(window.localStorage.getItem(STORE_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function storeWrite(patch) {
    try {
      var current = storeRead();
      Object.keys(patch).forEach(function (k) { current[k] = patch[k]; });
      window.localStorage.setItem(STORE_KEY, JSON.stringify(current));
    } catch (e) { /* storage may be unavailable: picker still works */ }
  }

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }
  function formatSize(bytes) {
    if (!bytes) { return '0 KB'; }
    if (bytes < 1024 * 1024) { return Math.max(1, Math.round(bytes / 1024)) + ' KB'; }
    if (bytes < 1024 * 1024 * 1024) { return (bytes / 1048576).toFixed(1) + ' MB'; }
    return (bytes / 1073741824).toFixed(2) + ' GB';
  }
  function formatDate(seconds) {
    if (!seconds) { return ''; }
    var d = new Date(seconds * 1000);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }
  function fetchJSON(url, options) {
    return fetch(url, Object.assign({ credentials: 'same-origin' }, options || {})).then(function (response) {
      return response.json().catch(function () { return { ok: false, error: 'Unexpected server response (' + response.status + ').' }; })
        .then(function (data) { data._status = response.status; return data; });
    });
  }
  function postJSON(url, body) {
    return fetchJSON(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
    }).then(function (data) {
      if (data && data.ok === false) { var err = new Error(data.error || 'Request failed.'); err.data = data; throw err; }
      return data;
    });
  }

  function open(options) {
    options = options || {};
    var kind = options.kind || 'any';
    var multiple = !!options.multiple;
    var saved = storeRead();
    var state = {
      path: '', sort: saved.sort || 'name', order: saved.order || 'asc', showHidden: false, showAll: false,
      query: '', view: saved.view || (kind === 'image' ? 'grid' : 'list'), offset: 0, entries: [],
      hasMore: false, total: 0, selected: {}, roots: [], loadToken: 0
    };

    return new Promise(function (resolve) {
      var root = make('div', 'becss-filepicker becss-filepicker--open');
      root.setAttribute('role', 'dialog');
      root.setAttribute('aria-modal', 'true');

      var panel = make('div', 'becss-filepicker__panel');
      var header = make('div', 'becss-filepicker__header');
      var titleWrap = make('h2', 'becss-filepicker__title', options.title || KIND_TITLES[kind] || 'Select files');
      var subtitle = make('span', 'becss-filepicker__subtitle',
        options.subtitle || (multiple ? 'Tap files to select several - you can change folders and keep selecting.' : 'Tap a file to select it.'));
      titleWrap.appendChild(subtitle);
      var closeButton = make('button', 'becss-filepicker__close', '×');
      closeButton.type = 'button';
      closeButton.setAttribute('aria-label', 'Close');
      header.appendChild(titleWrap);
      header.appendChild(closeButton);

      var locations = make('div', 'becss-filepicker__locations');

      var pathbar = make('div', 'becss-filepicker__pathbar');
      var upButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small', '↑ Up');
      upButton.type = 'button';
      var crumbs = make('div', 'becss-filepicker__crumbs');
      var refreshButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small', '↻');
      refreshButton.type = 'button';
      refreshButton.setAttribute('aria-label', 'Refresh');
      pathbar.appendChild(upButton);
      pathbar.appendChild(crumbs);
      pathbar.appendChild(refreshButton);

      var tools = make('div', 'becss-filepicker__tools');
      var search = make('input', 'becss-filepicker__search');
      search.type = 'search';
      search.placeholder = 'Filter this folder...';
      var sortSelect = make('select', 'becss-filepicker__select');
      [['name', 'Name'], ['date', 'Date'], ['size', 'Size']].forEach(function (pair) {
        var opt = make('option', null, pair[1]); opt.value = pair[0]; sortSelect.appendChild(opt);
      });
      sortSelect.value = state.sort;
      var orderButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small');
      orderButton.type = 'button';
      var viewButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small');
      viewButton.type = 'button';
      function makeToggle(label) {
        var wrap = make('label', 'becss-filepicker__toggle');
        var box = document.createElement('input'); box.type = 'checkbox';
        wrap.appendChild(box); wrap.appendChild(document.createTextNode(label));
        return { wrap: wrap, box: box };
      }
      var hiddenToggle = makeToggle('Hidden');
      var allToggle = makeToggle('All types');
      [search, sortSelect, orderButton, viewButton, hiddenToggle.wrap, allToggle.wrap].forEach(function (n) { tools.appendChild(n); });

      var list = make('div', 'becss-filepicker__list');

      var footer = make('div', 'becss-filepicker__footer');
      var summary = make('div', 'becss-filepicker__summary');
      var selectAllButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small', 'Select all');
      selectAllButton.type = 'button';
      var clearButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--small', 'Clear');
      clearButton.type = 'button';
      var cancelButton = make('button', 'becss-filepicker__btn', 'Cancel');
      cancelButton.type = 'button';
      var confirmButton = make('button', 'becss-filepicker__btn becss-filepicker__btn--primary');
      confirmButton.type = 'button';
      footer.appendChild(summary);
      if (multiple) { footer.appendChild(selectAllButton); footer.appendChild(clearButton); }
      footer.appendChild(cancelButton);
      footer.appendChild(confirmButton);

      [header, locations, pathbar, tools, list, footer].forEach(function (n) { panel.appendChild(n); });
      root.appendChild(panel);
      document.body.appendChild(root);
      document.body.classList.add('becss-filepicker-lock');

      /* ---------- helpers ---------- */
      function selectedList() { return Object.keys(state.selected).map(function (p) { return state.selected[p]; }); }
      function updateFooter() {
        var picked = selectedList();
        var total = picked.reduce(function (sum, f) { return sum + (f.size || 0); }, 0);
        summary.textContent = '';
        var strong = make('strong', null, String(picked.length));
        summary.appendChild(strong);
        summary.appendChild(document.createTextNode(' selected' + (picked.length ? ' · ' + formatSize(total) : '')));
        confirmButton.disabled = picked.length === 0;
        confirmButton.textContent = options.confirmLabel || (multiple ? 'Import ' + (picked.length || '') : 'Choose');
        orderButton.textContent = state.order === 'asc' ? '↑ A→Z' : '↓ Z→A';
        viewButton.textContent = state.view === 'grid' ? '☰ List' : '▦ Grid';
        selectAllButton.disabled = !state.entries.some(function (e) { return e.selectable; });
      }
      function finish(result) {
        document.removeEventListener('keydown', onKey, true);
        document.body.classList.remove('becss-filepicker-lock');
        if (root.parentNode) { root.parentNode.removeChild(root); }
        resolve(result);
      }
      function onKey(ev) { if (ev.key === 'Escape') { ev.stopPropagation(); finish(null); } }
      document.addEventListener('keydown', onKey, true);

      function renderCrumbs(listing) {
        crumbs.textContent = '';
        var homeCrumb = make('button', 'becss-filepicker__crumb' + (listing.path ? '' : ' becss-filepicker__crumb--current'), 'Locations');
        homeCrumb.type = 'button';
        homeCrumb.addEventListener('click', function () { navigate(''); });
        crumbs.appendChild(homeCrumb);
        (listing.crumbs || []).forEach(function (crumb, index, all) {
          crumbs.appendChild(make('span', 'becss-filepicker__crumb-sep', '›'));
          var button = make('button', 'becss-filepicker__crumb' + (index === all.length - 1 ? ' becss-filepicker__crumb--current' : ''), crumb.name);
          button.type = 'button';
          button.addEventListener('click', function () { navigate(crumb.path); });
          crumbs.appendChild(button);
        });
        crumbs.scrollLeft = crumbs.scrollWidth;
      }

      function renderLocations() {
        locations.textContent = '';
        state.roots.forEach(function (rootInfo) {
          var chip = make('button', 'becss-filepicker__chip', rootInfo.label);
          chip.type = 'button';
          chip.addEventListener('click', function () { navigate(rootInfo.path); });
          locations.appendChild(chip);
          (rootInfo.shortcuts || []).forEach(function (shortcut) {
            var shortcutChip = make('button', 'becss-filepicker__chip becss-filepicker__chip--shortcut', shortcut.label);
            shortcutChip.type = 'button';
            shortcutChip.title = rootInfo.label + ' / ' + shortcut.label;
            shortcutChip.addEventListener('click', function () { navigate(shortcut.path); });
            locations.appendChild(shortcutChip);
          });
        });
      }

      function buildRow(entry) {
        var grid = state.view === 'grid';
        var selected = !!state.selected[entry.path];
        var row = make('button', 'becss-filepicker__row' + (grid ? ' becss-filepicker__row--grid' : '')
          + (selected ? ' becss-filepicker__row--selected' : '')
          + (!entry.is_dir && !entry.selectable ? ' becss-filepicker__row--disabled' : ''));
        row.type = 'button';
        row.dataset.path = entry.path;

        var icon = make('span', 'becss-filepicker__icon' + (grid ? ' becss-filepicker__icon--grid' : ''));
        var showThumb = entry.thumb && entry.selectable && (grid || kind === 'image');
        if (showThumb) {
          var img = document.createElement('img');
          img.className = 'becss-filepicker__thumb';
          img.loading = 'lazy';
          img.decoding = 'async';
          img.alt = '';
          img.src = API + '/thumb?path=' + encodeURIComponent(entry.path);
          img.addEventListener('error', function () { icon.textContent = ICONS[entry['class']] || ICONS.other; });
          icon.appendChild(img);
        } else {
          icon.textContent = ICONS[entry['class']] || ICONS.other;
        }
        var meta = make('span', 'becss-filepicker__meta');
        meta.appendChild(make('span', 'becss-filepicker__name' + (grid ? ' becss-filepicker__name--wrap' : ''), entry.name));
        if (!grid) {
          meta.appendChild(make('span', 'becss-filepicker__detail',
            entry.is_dir ? 'Folder' : (formatSize(entry.size) + (entry.modified ? ' · ' + formatDate(entry.modified) : ''))));
        } else if (!entry.is_dir) {
          meta.appendChild(make('span', 'becss-filepicker__detail', formatSize(entry.size)));
        }
        row.appendChild(icon);
        row.appendChild(meta);
        if (!entry.is_dir && entry.selectable) {
          row.appendChild(make('span', 'becss-filepicker__check', '✓'));
        }
        row.addEventListener('click', function () { onRowActivate(entry, row); });
        row.addEventListener('dblclick', function () {
          if (!multiple && !entry.is_dir && entry.selectable) { state.selected = {}; toggle(entry); finish(buildResult()); }
        });
        return row;
      }

      function toggle(entry) {
        if (state.selected[entry.path]) {
          delete state.selected[entry.path];
        } else {
          if (!multiple) { state.selected = {}; }
          state.selected[entry.path] = { path: entry.path, name: entry.name, size: entry.size };
        }
      }
      function onRowActivate(entry, row) {
        if (entry.is_dir) { navigate(entry.path); return; }
        if (!entry.selectable) { return; }
        toggle(entry);
        if (multiple) {
          row.classList.toggle('becss-filepicker__row--selected', !!state.selected[entry.path]);
        } else {
          Array.prototype.forEach.call(list.querySelectorAll('.becss-filepicker__row--selected'),
            function (n) { n.classList.remove('becss-filepicker__row--selected'); });
          row.classList.toggle('becss-filepicker__row--selected', !!state.selected[entry.path]);
        }
        updateFooter();
      }

      function renderList(append) {
        if (!append) { list.textContent = ''; }
        list.classList.toggle('becss-filepicker__list--grid', state.view === 'grid');
        var oldMore = list.querySelector('.becss-filepicker__more');
        if (oldMore) { oldMore.remove(); }
        var startIndex = append ? list.querySelectorAll('.becss-filepicker__row').length : 0;
        var fragment = document.createDocumentFragment();
        state.entries.slice(startIndex).forEach(function (entry) { fragment.appendChild(buildRow(entry)); });
        list.appendChild(fragment);
        if (!state.entries.length) {
          list.appendChild(make('div', 'becss-filepicker__message',
            state.path ? 'Nothing to show here. Try "All types" or "Hidden", or pick another folder.' : ''));
        }
        if (state.hasMore) {
          var more = make('button', 'becss-filepicker__btn becss-filepicker__more',
            'Load more (' + state.entries.length + ' of ' + state.total + ')');
          more.type = 'button';
          more.addEventListener('click', function () { load(true); });
          list.appendChild(more);
        }
        updateFooter();
      }

      function showMessage(text, isError) {
        list.textContent = '';
        list.classList.remove('becss-filepicker__list--grid');
        list.appendChild(make('div', 'becss-filepicker__message' + (isError ? ' becss-filepicker__message--error' : ''), text));
      }

      function showRootsView(hint) {
        state.entries = []; state.total = 0; state.hasMore = false;
        renderCrumbs({ path: '', crumbs: [] });
        list.textContent = '';
        list.classList.remove('becss-filepicker__list--grid');
        var note = state.roots.length
          ? 'Choose a location above to start browsing.'
          : (hint || 'No browsable storage found.');
        list.appendChild(make('div', 'becss-filepicker__message', note));
        updateFooter();
      }

      function navigate(path) { state.path = path; state.offset = 0; load(false); }

      function load(append) {
        if (!state.path) { showRootsView(state.hint); return; }
        var token = ++state.loadToken;
        if (!append) { state.offset = 0; showMessage('Loading...'); }
        var query = '?path=' + encodeURIComponent(state.path) + '&kind=' + encodeURIComponent(kind)
          + '&sort=' + state.sort + '&order=' + state.order + '&offset=' + (append ? state.entries.length : 0)
          + '&limit=' + PAGE_SIZE + '&hidden=' + (state.showHidden ? 1 : 0) + '&all=' + (state.showAll ? 1 : 0)
          + '&q=' + encodeURIComponent(state.query);
        fetchJSON(API + '/list' + query).then(function (listing) {
          if (token !== state.loadToken) { return; }
          if (!listing.ok) {
            showMessage(listing.error || 'Could not open this folder.', true);
            renderCrumbs({ path: state.path, crumbs: [] });
            return;
          }
          state.path = listing.path;
          state.entries = append ? state.entries.concat(listing.entries) : listing.entries;
          state.hasMore = listing.has_more;
          state.total = listing.total;
          state.parent = listing.parent;
          var remembered = {}; remembered['dir_' + kind] = listing.path; storeWrite(remembered);
          renderCrumbs(listing);
          renderList(append);
          if (listing.truncated) {
            list.appendChild(make('div', 'becss-filepicker__message', 'Very large folder: only the first entries were scanned. Use the filter box.'));
          }
        }).catch(function () {
          if (token === state.loadToken) { showMessage('Could not reach the CMS server.', true); }
        });
      }

      function buildResult() {
        var files = selectedList();
        return { paths: files.map(function (f) { return f.path; }), files: files };
      }

      /* ---------- events ---------- */
      closeButton.addEventListener('click', function () { finish(null); });
      cancelButton.addEventListener('click', function () { finish(null); });
      confirmButton.addEventListener('click', function () { if (selectedList().length) { finish(buildResult()); } });
      clearButton.addEventListener('click', function () { state.selected = {}; renderList(false); });
      selectAllButton.addEventListener('click', function () {
        state.entries.forEach(function (e) {
          if (e.selectable) { state.selected[e.path] = { path: e.path, name: e.name, size: e.size }; }
        });
        renderList(false);
      });
      upButton.addEventListener('click', function () { navigate(state.parent || ''); });
      refreshButton.addEventListener('click', function () { load(false); });
      sortSelect.addEventListener('change', function () { state.sort = sortSelect.value; storeWrite({ sort: state.sort }); load(false); });
      orderButton.addEventListener('click', function () { state.order = state.order === 'asc' ? 'desc' : 'asc'; storeWrite({ order: state.order }); load(false); });
      viewButton.addEventListener('click', function () { state.view = state.view === 'grid' ? 'list' : 'grid'; storeWrite({ view: state.view }); renderList(false); });
      hiddenToggle.box.addEventListener('change', function () { state.showHidden = hiddenToggle.box.checked; load(false); });
      allToggle.box.addEventListener('change', function () { state.showAll = allToggle.box.checked; load(false); });
      var searchTimer = null;
      search.addEventListener('input', function () {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(function () { state.query = search.value; load(false); }, 250);
      });

      /* ---------- start ---------- */
      updateFooter();
      showMessage('Loading locations...');
      fetchJSON(API + '/roots').then(function (data) {
        if (!data.ok) { showMessage(data.error || 'File browser unavailable.', true); return; }
        state.roots = data.roots || [];
        state.hint = data.hint;
        renderLocations();
        var start = saved['dir_' + kind];
        if (start) { state.path = start; load(false); }
        else if (state.roots.length) { state.path = state.roots[0].path; load(false); }
        else { showRootsView(data.hint); }
      }).catch(function () { showMessage('Could not reach the CMS server.', true); });
    });
  }

  /* ---------- declarative binder ---------- */
  document.addEventListener('click', function (ev) {
    var trigger = ev.target.closest ? ev.target.closest('[data-fb-pick]') : null;
    if (!trigger) { return; }
    ev.preventDefault();
    var data = trigger.dataset;
    open({
      kind: data.fbKind || 'any', multiple: data.fbMultiple === '1',
      title: data.fbTitle || undefined, confirmLabel: data.fbConfirm || undefined
    }).then(function (result) {
      if (!result) { return; }
      if (data.fbTarget) {
        var target = document.querySelector(data.fbTarget);
        if (target) { target.value = result.paths.join('\n'); }
      }
      if (data.fbSummary) {
        var box = document.querySelector(data.fbSummary);
        if (box) {
          box.textContent = '';
          result.files.forEach(function (f) {
            box.appendChild(make('span', 'becss-fb-summary__item', f.name + ' (' + formatSize(f.size) + ')'));
          });
        }
      }
      trigger.dispatchEvent(new CustomEvent('fb:picked', { bubbles: true, detail: result }));
    });
  });

  window.CMSFilePicker = { open: open, postJSON: postJSON, formatSize: formatSize, version: '18.29' };
})();
