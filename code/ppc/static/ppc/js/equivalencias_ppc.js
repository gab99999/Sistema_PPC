(() => {
  const cfg = JSON.parse(document.getElementById('eq-config').textContent);
  const csrf = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))?.split('=')[1] || '';
  const initial = JSON.parse(document.getElementById('eq-pares-iniciais').textContent || '[]');
  const automaticas = JSON.parse(document.getElementById('eq-automaticas').textContent || '[]');
  const key = (novo, matriz, antigo) => `${novo}|${matriz}|${antigo}`;
  const selecionadas = new Set(initial.map((p) => key(p[0], p[1], p[2])));
  const originais = new Set(selecionadas);
  const cache = new Map();
  let celula = null, offset = 0, termo = '', timer = null;
  const paramsForCell = (extra = {}) => new URLSearchParams({
    item_id: celula.dataset.novo, matriz_anterior_id: celula.dataset.anterior,
    offset: String(extra.offset || 0), q: extra.q || '',
  });
  const selectedIn = (c) => [...selecionadas].filter((p) => p.startsWith(`${c.dataset.novo}|${c.dataset.anterior}|`)).map((p) => p.split('|')[2]);

  function setDirty() {
    const sujo = [...selecionadas].sort().join(',') !== [...originais].sort().join(',');
    document.getElementById('eq-dirty').textContent = sujo ? 'Alterações não salvas' : 'Salvo';
    count();
  }
  function count() {
    const rows = [...document.querySelectorAll('.eq-linha')];
    const com = rows.filter((row) => [...row.querySelectorAll('.eq-celula')].some((c) => selectedIn(c).length)).length;
    document.getElementById('eq-contador').textContent = `${com} de ${rows.length} com equivalência`;
  }
  function renderCell(c) {
    const oldChips = new Map([...c.querySelectorAll('.eq-chip')].map((x) => [x.dataset.itemId, { text: x.textContent, automatic: x.title === 'Automática' }]));
    const box = c.querySelector('.eq-selecionados');
    box.replaceChildren();
    const ids = selectedIn(c);
    if (!ids.length) {
      const empty = document.createElement('span'); empty.className = 'eq-vazio'; empty.textContent = '—'; box.append(empty);
    }
    ids.forEach((id) => {
      const info = cache.get(String(id));
      const chip = document.createElement('span'); chip.className = 'eq-chip'; chip.dataset.itemId = id;
      const old = oldChips.get(String(id));
      chip.textContent = info ? `${info.codigo || id} · ${info.carga} h` : (old?.text || `${id}`);
      const automatic = info ? info.automatica : Boolean(old?.automatic);
      chip.classList.add(automatic ? 'eq-chip-auto' : 'eq-chip-manual'); chip.title = automatic ? 'Automática' : 'Manual';
      box.append(chip);
    });
    c.querySelector('.eq-editar-celula').textContent = ids.length ? 'Editar equivalência' : 'Selecionar equivalência';
    const suggestions = (c.dataset.sugestaoIds || '').split(',').filter(Boolean);
    const pending = suggestions.some((id) => !ids.includes(id));
    const marker = c.querySelector('.eq-sugestao'); if (marker) { marker.hidden = !pending; marker.textContent = pending ? 'Sugestão automática · não aceita' : 'Sugestões automáticas aceitas'; }
    const row = c.closest('.eq-linha');
    row.classList.toggle('eq-sem-equivalencia', [...row.querySelectorAll('.eq-celula')].every((x) => !selectedIn(x).length));
  }
  function filterRows() {
    const q = document.getElementById('eq-busca').value.trim().toLocaleLowerCase('pt-BR');
    const filter = document.getElementById('eq-filtro').value;
    document.querySelectorAll('.eq-linha').forEach((row) => {
      const cells = [...row.querySelectorAll('.eq-celula')];
      const has = cells.some((c) => selectedIn(c).length > 0);
      const suggestion = cells.some((c) => Number(c.dataset.sugestoes) > 0);
      const matches = `${row.dataset.nome} ${row.dataset.codigo}`.includes(q)
        && (filter === 'todos' || (filter === 'com' && has) || (filter === 'sem' && !has) || (filter === 'sugestao' && suggestion));
      row.hidden = !matches || row.dataset.periodClosed === 'true';
    });
  }
  function candidateNode(c) {
    cache.set(String(c.id), c);
    const node = document.createElement('div'); node.className = 'eq-candidato'; node.dataset.candidato = c.id;
    const label = document.createElement('label');
    const input = document.createElement('input'); input.type = 'checkbox'; input.disabled = !c.elegivel;
    input.checked = selecionadas.has(key(celula.dataset.novo, celula.dataset.anterior, c.id));
    input.addEventListener('change', () => {
      const pair = key(celula.dataset.novo, celula.dataset.anterior, c.id);
      if (input.checked) selecionadas.add(pair); else selecionadas.delete(pair);
      setDirty();
    });
    const text = document.createElement('span');
    text.textContent = `${c.codigo || 'Sem código'} — ${c.nome} · ${c.carga ?? '—'} h · ${c.periodo}º período`;
    label.append(input, text); node.append(label);
    if (!c.elegivel) { const reason = document.createElement('small'); reason.className = 'ajuda-campo'; reason.textContent = c.motivo; node.append(reason); }
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Ver ementa';
    const ementa = document.createElement('p'); ementa.textContent = c.ementa || 'Ementa não cadastrada.'; details.append(summary, ementa); node.append(details);
    return node;
  }
  async function loadCandidates(next = 0, append = false) {
    if (!celula) return;
    offset = next;
    const box = document.getElementById('eq-candidatos');
    if (!append) box.textContent = 'Consultando componentes...';
    const response = await fetch(`${cfg.candidatos}?${paramsForCell({ offset, q: termo })}`);
    const data = await response.json();
    if (!response.ok) { box.textContent = data.erro || 'Erro ao consultar candidatos.'; return; }
    if (!append) box.replaceChildren();
    data.candidatos.forEach((c) => box.append(candidateNode(c)));
    document.getElementById('eq-mais').hidden = !data.mais;
  }
  async function openCell(c) {
    celula = c; termo = '';
    document.getElementById('eq-candidato-busca').value = '';
    const row = c.closest('.eq-linha');
    document.getElementById('eq-editor-titulo').textContent = `${row.querySelector('.eq-primeira-coluna strong').textContent} — ${c.dataset.anteriorNome}`;
    document.getElementById('eq-editor').showModal(); await loadCandidates();
  }
  document.querySelectorAll('.eq-editar-celula').forEach((b) => b.addEventListener('click', () => openCell(b.closest('.eq-celula'))));
  document.getElementById('eq-candidato-busca').addEventListener('input', () => {
    clearTimeout(timer); timer = setTimeout(() => { termo = document.getElementById('eq-candidato-busca').value; loadCandidates(); }, 250);
  });
  document.getElementById('eq-mais').addEventListener('click', () => loadCandidates(offset + 50, true));
  document.getElementById('eq-concluir').addEventListener('click', () => {
    if (celula) renderCell(celula); document.getElementById('eq-editor').close(); setDirty(); filterRows();
  });
  function restoreCell() {
    if (!celula) return;
    const n = celula.dataset.novo, m = celula.dataset.anterior;
    [...selecionadas].forEach((p) => { if (p.startsWith(`${n}|${m}|`)) selecionadas.delete(p); });
    automaticas.filter((p) => String(p[0]) === n && String(p[1]) === m).forEach((p) => selecionadas.add(key(p[0], p[1], p[2])));
    renderCell(celula); loadCandidates(); setDirty();
  }
  document.getElementById('eq-restaurar-celula').addEventListener('click', restoreCell);
  document.getElementById('eq-restaurar').addEventListener('click', () => {
    selecionadas.clear(); automaticas.forEach((p) => selecionadas.add(key(p[0], p[1], p[2])));
    document.querySelectorAll('.eq-celula').forEach(renderCell); setDirty(); filterRows();
  });
  document.getElementById('eq-busca').addEventListener('input', filterRows);
  document.getElementById('eq-filtro').addEventListener('change', filterRows);
  document.querySelectorAll('.eq-toggle-periodo').forEach((b) => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') === 'true'; b.setAttribute('aria-expanded', String(!open));
    b.textContent = `${open ? '▸' : '▾'} ${b.textContent.slice(2)}`;
    b.closest('tbody').querySelectorAll('.eq-linha').forEach((row) => { row.dataset.periodClosed = String(open); }); filterRows();
  }));
  async function preview() {
    const pairs = [...selecionadas].map((p) => { const [n, m, a] = p.split('|').map(Number); return [n, a]; });
    const response = await fetch(cfg.previa, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ pares: pairs, preview: true }) });
    const data = await response.json();
    document.getElementById('eq-previa-conteudo').innerHTML = data.html || data.erro;
    document.getElementById('eq-previa-dialog').showModal();
  }
  document.getElementById('eq-previa').addEventListener('click', preview);
  async function save() {
    const button = document.getElementById('eq-salvar'); button.disabled = true;
    try {
      const pairs = [...selecionadas].map((p) => { const [n, m, a] = p.split('|').map(Number); return [n, a]; });
      const response = await fetch(cfg.salvar, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ pares: pairs }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.erro || 'Não foi possível salvar.');
      originais.clear(); selecionadas.forEach((p) => originais.add(p));
      document.querySelectorAll('.eq-celula').forEach(renderCell); setDirty(); filterRows();
    } catch (error) { alert(error.message); } finally { button.disabled = false; }
  }
  document.getElementById('eq-salvar').addEventListener('click', save);
  document.getElementById('eq-salvar-previa').addEventListener('click', async () => { document.getElementById('eq-previa-dialog').close(); await save(); });
  document.getElementById('eq-imprimir').addEventListener('click', () => {
    const win = window.open('', '_blank'); if (!win) return alert('Permita janelas pop-up para imprimir ou salvar em PDF.');
    win.document.write('<!doctype html><html><head><meta charset="utf-8"><title>Equivalências Curriculares</title><style>@page{size:A4 landscape;margin:12mm}body{font:12px Arial}table{width:100%;border-collapse:collapse}td,th{border:1px solid #bbb;padding:5px}tr{break-inside:avoid}</style></head><body>' + document.getElementById('eq-previa-conteudo').innerHTML + '</body></html>'); win.document.close(); win.focus(); win.print();
  });
  document.querySelectorAll('[data-fechar]').forEach((b) => b.addEventListener('click', () => document.getElementById(b.dataset.fechar).close()));
  document.querySelectorAll('.eq-toggle-periodo[aria-expanded="false"]').forEach((b) => b.closest('tbody').querySelectorAll('.eq-linha').forEach((row) => { row.dataset.periodClosed = 'true'; row.hidden = true; }));
  document.querySelectorAll('.eq-celula').forEach((c) => {
    const row = c.closest('.eq-linha'); row.classList.toggle('eq-sem-equivalencia', [...row.querySelectorAll('.eq-celula')].every((x) => !selectedIn(x).length));
  });
  count();
  window.addEventListener('beforeunload', (event) => {
    if ([...selecionadas].sort().join(',') !== [...originais].sort().join(',')) { event.preventDefault(); event.returnValue = ''; }
  });
})();
