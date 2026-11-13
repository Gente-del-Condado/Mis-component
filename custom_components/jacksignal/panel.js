/* Panel nativo de JackSignal. Sin dependencias externas ni HTML de usuario. */
const labels = {low: 'Baja · P0', normal: 'Normal · P1', high: 'Alta · P2', critical: 'Crítica · P3'};
const modes = {never: 'Nunca', disarmed: 'Solo con alarma desarmada', always: 'Siempre, sin requerir Alarmo'};
const triggers = {manual: 'Solo manual', change: 'Cada cambio de valor', above: 'Al superar un umbral', below: 'Al bajar de un umbral'};
const fold = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
function node(tag, text, attrs = {}) {
  const el = document.createElement(tag);
  if (text !== null) el.textContent = text;
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}
function soundName(selection) {
  return selection?.media_content_id?.replace('media-source://media_source/', '') || 'Sin sonido asignado';
}
function healthLabel(health) {
  return ({available:'Disponible en Home Assistant',unavailable:'No disponible',unknown:'Estado desconocido',missing:'Entidad no encontrada'})[health?.availability] || 'Sin datos de disponibilidad';
}
function sensorStateText(row) {
  if (row.state == null) return 'Entidad no encontrada';
  if (row.state === 'unavailable') return 'No disponible';
  if (row.state === 'unknown') return 'Estado desconocido';
  if (row.kind === 'sensor') {
    if (row.state.toLowerCase() === row.rule.open_state) return 'Abierto / activado';
    if (row.state.toLowerCase() === row.rule.closed_state) return 'Cerrado / desactivado';
  }
  return row.state;
}
function timestampText(value,timeZone,now=Date.now()) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Sin registro';
  const date = new Date(value), seconds = Math.max(0,Math.floor((now-date.getTime())/1000));
  const ago = seconds < 60 ? `hace ${seconds} s` : seconds < 3600 ? `hace ${Math.floor(seconds/60)} min` : seconds < 86400 ? `hace ${Math.floor(seconds/3600)} h` : `hace ${Math.floor(seconds/86400)} días`;
  let formatted;
  try {formatted = new Intl.DateTimeFormat('es-ES',{dateStyle:'short',timeStyle:'medium',timeZone}).format(date);}
  catch {formatted = date.toISOString();}
  return `${formatted} · ${ago}`;
}
function noticeGroups(rows,kind,query,filter,availability='all') {
  const groups = new Map();
  for (const row of rows) {
    if (kind === 'sensor' ? row.kind === 'alarm' : row.kind !== kind) continue;
    if (!groups.has(row.key)) groups.set(row.key,[]);
    groups.get(row.key).push(row);
  }
  return [...groups.values()].filter(group =>
    (availability === 'all' || group.some(row => row.health?.availability === availability)) &&
    group.some(row => filter === 'all' || row.status === filter) &&
    group.some(row => fold([row.name,row.key,soundName(row.rule.sound),soundName(row.rule.close_sound),row.rule.before,row.rule.after,...Object.values(row.rule.state_labels || {})].join(' ')).includes(query)));
}
class JackSignalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this.selected = new Set(); this.kind = 'sensor'; this.limit = 60; this.cards = new Map(); this.busy = false;
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#17212b);background:var(--primary-background-color,#f5f7fa);font:16px/1.5 var(--paper-font-body1_-_font-family,system-ui)}
        *{box-sizing:border-box} [hidden]{display:none!important}
        header{display:flex;align-items:center;gap:12px;padding:16px 24px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#d5dae0)}
        h1{font-size:1.6rem;margin:0}h2,h3{font-size:1.15rem;margin:0}p{margin:.5rem 0}main{max-width:1160px;margin:auto;padding:24px}
        .muted{color:var(--secondary-text-color,#526171)}.tools,.actions,.nav{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.tools{justify-content:space-between;margin-bottom:20px}
        a{color:var(--primary-color,#006a96)}button,input,select{font:inherit;font-size:max(1rem,1em);color:inherit}button,a.button{min-height:48px;padding:10px 16px;border:1px solid var(--divider-color,#9ca9b5);border-radius:9px;background:var(--card-background-color,#fff);cursor:pointer;text-decoration:none}
        button:hover:not(:disabled){border-color:var(--primary-color,#00789a)}button[aria-pressed=true],button.primary{background:var(--primary-color,#00789a);color:var(--text-primary-color,#fff);border-color:transparent}
        button:disabled{opacity:.55;cursor:default} :focus-visible{outline:3px solid var(--primary-color,#00789a);outline-offset:3px}
        search{display:block;margin:20px 0} .filters{display:flex;flex-wrap:wrap;gap:16px;align-items:end}.field{display:flex;flex-direction:column;gap:5px;margin-bottom:14px;min-width:0}.filters .field{flex:1;min-width:190px;margin:0}
        input:not([type=checkbox]),select{width:100%;min-height:48px;padding:10px;border:1px solid var(--secondary-text-color,#64717f);border-radius:8px;background:var(--card-background-color,#fff)}
        .check{display:flex;align-items:center;gap:10px;min-height:48px;margin:8px 0}input[type=checkbox]{width:22px;height:22px;accent-color:var(--primary-color,#00789a)}
        #cards{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:16px}li{min-width:0}article{padding:20px;border:1px solid var(--divider-color,#d5dae0);border-radius:14px;background:var(--card-background-color,#fff);overflow-wrap:anywhere}
        #cards.compact{grid-template-columns:1fr}.notice-types{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}#cards header{flex-wrap:wrap;border-radius:12px;margin-bottom:10px}h4{margin:0 0 8px}
        .sensor-health{padding:16px 20px;margin-bottom:12px;border:1px solid var(--divider-color,#b7c1cb);border-inline-start:4px solid var(--primary-color,#00789a);border-radius:12px;background:var(--card-background-color,#fff)}
        .sensor-health[data-availability=unavailable],.sensor-health[data-availability=missing]{border-inline-start-color:var(--error-color,#b3261e)}
        .health-times{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px;margin:12px 0}.health-times dt{font-size:.85rem;color:var(--secondary-text-color,#526171)}.health-times dd{margin:4px 0 0;font-variant-numeric:tabular-nums}.sensor-health>.muted{font-size:.85rem}.nav{padding:6px;background:var(--secondary-background-color,#eef2f5);border-radius:12px}.nav button{flex:1}.help{padding:0 14px;border:1px solid var(--divider-color,#b7c1cb);border-radius:10px}
        .history{padding:0 16px;border:1px solid var(--divider-color,#b7c1cb);border-radius:12px;background:var(--card-background-color,#fff)}.history-list{max-height:480px;overflow:auto;padding-inline-start:24px}.history-entry{padding:12px 8px;border-bottom:1px solid var(--divider-color,#d5dae0)}.history-entry p{margin:4px 0}.history-entry time{font-size:.85rem}.history>.muted{font-size:.9rem}
        .badge{display:inline-block;font-size:.85rem;border:1px solid var(--divider-color,#b7c1cb);border-radius:20px;padding:3px 10px;margin:8px 0}.summary{min-height:75px}.warning{border-inline-start:3px solid var(--warning-color,#a56b00);padding-inline-start:10px;font-size:.9rem}.actions{margin-top:16px}
        #message{min-height:30px;padding:6px 0}.empty{padding:32px;text-align:center;border:1px dashed var(--divider-color,#b0bac4);border-radius:12px}
        dialog{width:min(620px,calc(100% - 24px));max-height:90dvh;padding:24px;border:1px solid var(--divider-color,#b0bac4);border-radius:16px;color:var(--primary-text-color,#17212b);background:var(--card-background-color,#fff)}
        dialog:modal{overscroll-behavior:contain}dialog::backdrop{background:#0008;overflow:hidden;overscroll-behavior:contain}
        fieldset{border:1px solid var(--divider-color,#b0bac4);border-radius:10px;padding:16px;margin:16px 0;min-width:0}legend{font-weight:600}details{margin:14px 0}summary{cursor:pointer;min-height:48px;padding:10px 0}
        #form-error{color:var(--error-color,#b3261e);min-height:24px}progress{width:100%}.id{font-size:.8rem;overflow-wrap:anywhere}.tip{padding:12px;border-radius:8px;background:var(--secondary-background-color,#eef2f5)}
        .overview{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}.metric{padding:14px 18px;border:1px solid var(--divider-color,#d5dae0);border-radius:12px;background:var(--card-background-color,#fff)}.metric strong{display:block;font-size:1.7rem}
        #live{border-inline-start:4px solid var(--primary-color,#00789a)}#batch-tools{padding:12px;border:1px solid var(--divider-color,#d5dae0);border-radius:10px;margin:14px 0}.compact article{padding:14px}.compact .summary{min-height:0}.compact .id{display:none}.compact .actions{gap:6px}.compact .actions button{padding:8px}.compact .summary p{font-size:.9rem;margin:4px 0}.selection{margin:0 0 8px}.phrase{font-size:1.1rem;white-space:pre-wrap}
        @media(max-width:600px){main{padding:16px}header{padding:12px}h1{font-size:1.3rem}.actions button{flex:1}dialog{padding:18px}}
      </style>
      <header lang="es"><ha-menu-button></ha-menu-button><div><h1>Gestionar avisos</h1><span class="muted">JackSignal · Audio con prioridades</span></div></header>
      <main lang="es">
        <div class="tools"><p id="panel-info" class="muted">Cargando configuración…</p><div class="actions"><a class="button" href="/config/integrations/integration/jacksignal">Configuración y audio</a><button id="refresh" type="button">Actualizar</button></div></div>
        <div class="overview" aria-label="Resumen de avisos"><div class="metric"><strong id="count-active">—</strong>Activados</div><div class="metric"><strong id="count-disabled">—</strong>Desactivados</div><div class="metric"><strong id="count-empty">—</strong>Sin configurar</div><div class="metric" id="live">Consultando reproducción…</div></div>
        <div class="nav" role="group" aria-label="Tipo de aviso"><button type="button" data-kind="sensor" aria-pressed="true">Sensores</button><button type="button" data-kind="alarm" aria-pressed="false">Alarmo</button><button type="button" data-kind="speech" aria-pressed="false">Solo voz</button></div>
        <details id="voice-general" class="tip" hidden><summary>Configuración general de voz y Piper</summary><p id="voice-general-info"></p><div class="actions"><button id="voice-defaults" type="button">Configurar voz general</button><button id="piper-prepare" type="button">Preparar Piper</button><a class="button" href="/config/integrations/dashboard">Conectar Wyoming</a><a id="piper-app" class="button" href="/hassio/addon/core_piper/info">Abrir Piper</a></div><p id="piper-status" role="status"></p></details>
        <details id="history-settings" class="tip"><summary id="history-settings-title">Historial: conservación y limpieza</summary><p id="history-settings-info"></p><form id="history-settings-form" aria-labelledby="history-settings-title"><div class="field"><label for="history-days">Días de conservación (1–365)</label><input id="history-days" name="days" type="number" min="1" max="365" step="1" required></div><p>Reducir los días elimina los registros más antiguos. Se mantiene un máximo de 1.000 registros entre todos los sensores, aunque no se haya alcanzado el plazo.</p><button id="history-save" type="submit">Guardar y aplicar retención</button></form><div id="history-clear-all"></div><p id="history-settings-message" role="status"></p></details>
        <p id="connection-status" class="muted" role="status">Consultando el estado de los sensores…</p><search aria-label="Buscar avisos"><div class="filters"><div class="field"><label for="query">Buscar por nombre, sensor o sonido</label><input id="query" type="search" name="query" placeholder="Por ejemplo, ventana del salón" autocapitalize="none" spellcheck="false"></div><div class="field"><label for="filter">Mostrar</label><select id="filter" name="filter"><option value="all">Todos</option><option value="configured">Configurados y activados</option><option value="unconfigured">Sin configurar</option><option value="disabled">Desactivados</option></select></div><div class="field" id="availability-field"><label for="availability-filter">Disponibilidad del sensor</label><select id="availability-filter" name="availability"><option value="all">Todas</option><option value="available">Disponible</option><option value="unavailable">No disponible</option><option value="unknown">Estado desconocido</option><option value="missing">Entidad no encontrada</option></select></div></div></search>
        <div class="actions"><button id="compact" type="button" aria-pressed="true">Vista compacta</button><button id="select-visible" type="button">Seleccionar configurados visibles</button><button id="clear-selection" type="button">Quitar selección</button></div>
        <div id="batch-tools" class="actions" hidden><span id="selection-count"></span><button id="batch-edit" type="button">Modificar selección</button></div>
        <details class="help"><summary>Cómo comprobar por qué no suena un aviso</summary><p>1. Comprueba la disponibilidad y si cambia el estado al mover el sensor. 2. Revisa la activación y las condiciones del aviso. 3. Consulta el diagnóstico de voz y las prioridades.</p><p>Las fechas pertenecen al estado actual de Home Assistant; no son un historial permanente y pueden reiniciarse al recrear la entidad. Las horas usan la zona horaria de Home Assistant.</p><p class="tip">Las pruebas son manuales, usan prioridad baja (P0) y no repiten el sonido. No activan Alarmo ni modifican el sensor. Puedes probar una regla desactivada sin activarla.</p></details>
        <button id="stop" type="button">Detener prueba</button><p id="message" role="status" aria-live="polite"></p><progress id="loading" aria-label="Cargando avisos"></progress>
        <h2 id="results" tabindex="-1">Avisos</h2><ul id="cards" role="list"></ul><p id="empty" class="empty" hidden>No hay avisos que coincidan. Cambia la búsqueda o el filtro.</p><button id="more" type="button" hidden>Mostrar más</button>
      </main>
      <dialog lang="es" aria-labelledby="edit-title"><h2 id="edit-title" tabindex="-1">Editar aviso</h2><p id="edit-help" class="muted"></p><form id="editor" aria-labelledby="edit-title"><div id="fields"></div><p id="form-error" role="status" aria-live="polite" tabindex="-1"></p><div class="actions"><button id="save" class="primary" type="submit">Guardar cambios</button><button id="cancel" type="button">Cancelar</button></div></form></dialog>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.shadowRoot.querySelectorAll('[data-kind]').forEach(btn => btn.addEventListener('click', () => {
      this.selected.clear(); this.kind = btn.dataset.kind; this.limit = 60; this.renderList();
    }));
    this.$('query').addEventListener('input', () => {this.selected.clear(); this.limit = 60; this.renderList();});
    this.$('filter').addEventListener('change', () => {this.selected.clear(); this.limit = 60; this.renderList();});
    this.$('availability-filter').addEventListener('change', () => {this.selected.clear(); this.limit = 60; this.renderList();});
    this.$('refresh').addEventListener('click', () => this.load());
    this.$('more').addEventListener('click', () => {this.limit += 60; this.renderList();});
    this.$('stop').addEventListener('click', () => this.perform({action:'stop_test'}));
    this.$('cancel').addEventListener('click', () => this.dialog.close());
    this.$('editor').addEventListener('submit', e => {e.preventDefault(); this.save();});
    this.dialog = this.shadowRoot.querySelector('dialog');
    this.$('cards').classList.add('compact');
    this.$('compact').addEventListener('click', () => {const compact = this.$('cards').classList.toggle('compact'); this.$('compact').setAttribute('aria-pressed',String(compact));});
    this.$('clear-selection').addEventListener('click', () => {this.selected.clear(); this.renderList();});
    this.$('select-visible').addEventListener('click', () => {for (const row of this.visibleRows || []) if (row.configured && this.selected.size < 200) this.selected.add(`${row.kind}:${row.key}`); this.renderList();});
    this.$('voice-defaults').addEventListener('click', () => this.editDefaults());
    this.$('piper-prepare').addEventListener('click', () => this.preparePiper());
    this.$('history-days').addEventListener('input',()=>{this.historyDaysDirty=true;});
    this.$('history-settings-form').addEventListener('submit',e=>{e.preventDefault();this.saveHistorySettings();});
    this.$('history-clear-all').append(this.historyDeleteControls('all',null,async()=>{for(const box of this.shadowRoot.querySelectorAll('details[data-history]')) this.renderHistory(box,[],0);}));
    this.$('batch-edit').addEventListener('click', () => this.editBatch());
  }
  set hass(value) {
    this._hass = value;
    this.shadowRoot.querySelector('ha-menu-button').hass = value;
    if (this.isConnected && !this.data && !this.busy) this.load();
  }
  set narrow(value) {this.shadowRoot.querySelector('ha-menu-button').narrow = value;}
  connectedCallback() {
    if (this._hass && !this.data) this.load();
    this.poll = setInterval(() => this.pollStatus(),5000);
  }
  disconnectedCallback() {clearInterval(this.poll);}
  async pollStatus() {
    if (!this._hass || document.hidden || this.statusPending) return;
    this.statusPending = true;
    try {this.renderStatus(await this.request({action:'status',history_queries:[...this.shadowRoot.querySelectorAll('details[data-history][open]')].filter(box=>(this.visibleRows || []).some(row=>row.key===box.dataset.history)).slice(0,20).map(box=>this.historyRequest(box)),entities:[...new Set((this.visibleRows || []).filter(row => row.kind !== 'alarm').map(row => row.key))].slice(0,2000)})); this.connectionStatus('Estados actualizados cada 5 segundos · Pulsa Actualizar para recalcular la lista filtrada');}
    catch {this.$('live').textContent = 'Estado de reproducción no disponible'; this.connectionStatus('No se pudo actualizar. Los datos mostrados pueden estar desactualizados. Revisa la conexión con Home Assistant.');}
    finally {this.statusPending = false;}
  }
  connectionStatus(message) {
    const el = this.$('connection-status');
    if (el.textContent !== message) el.textContent = message;
  }
  renderStatus(status) {
    if (!status) return;
    for (const [key,items] of Object.entries(status.history || {})) {
      for (const box of this.shadowRoot.querySelectorAll('details[data-history]')) if (box.dataset.history === key && box.open) this.renderHistory(box,items.entries || items,items.total);
    }
    if (status.sensors && this.data) {
      for (const row of this.data.rows) if (status.sensors[row.key]) {row.health = status.sensors[row.key]; row.state = row.health.state;}
      this.renderHealth();
    }
    for (const el of this.shadowRoot.querySelectorAll('[data-speech-status]')) {
      if (status.speech?.[el.dataset.speechStatus]) el.textContent = status.speech[el.dataset.speechStatus];
    }
    this.$('live').textContent = status.active ? `${status.paused ? 'En pausa' : 'Reproduciendo'} · ${labels[status.priority]} · ${status.source}` : 'En reposo · Listo para reproducir';
  }
  renderHealth() {
    const timeZone = this._hass?.config?.time_zone;
    for (const box of this.shadowRoot.querySelectorAll('[data-sensor-health]')) {
      const row = this.data.rows.find(row => row.kind !== 'alarm' && row.key === box.dataset.sensorHealth);
      if (!row) continue;
      const health = row.health;
      box.querySelector('[data-availability]').textContent = healthLabel(health);
      box.dataset.availability = health?.availability || 'unknown';
      box.querySelector('[data-health-state]').textContent = `Estado interno: ${health?.state ?? '—'}`;
      for (const field of ['last_changed','last_updated','last_reported']) {
        const time = box.querySelector(`[data-time="${field}"]`);
        time.textContent = timestampText(health?.[field],timeZone);
        if (health?.[field]) time.setAttribute('datetime',health[field]); else time.removeAttribute('datetime');
      }
    }
    for (const el of this.shadowRoot.querySelectorAll('[data-current-state]')) {
      const row = this.data.rows.find(row => `${row.kind}:${row.key}` === el.dataset.currentState);
      if (row) el.textContent = `Ahora: ${sensorStateText(row)}`;
    }
  }
  healthCard(row) {
    const box = node('section',null,{class:'sensor-health','data-sensor-health':row.key});
    box.append(node('h4','1. Estado del sensor'),node('strong','',{'data-availability':''}),node('p','',{'data-health-state':'',class:'muted'}));
    const list = node('dl',null,{class:'health-times'});
    for (const [field,label] of [['last_changed','Último cambio de estado'],['last_updated','Última actualización de estado o atributos'],['last_reported','Último registro en Home Assistant']]) {
      const group = node('div');group.append(node('dt',label));
      const value = node('dd');value.append(node('time','',{'data-time':field}));group.append(value);list.append(group);
    }
    box.append(list,node('p','La disponibilidad es la que comunica Home Assistant. Un registro no confirma un mensaje Zigbee ni una conexión física. Un sensor puede estar sano y llevar horas sin cambiar.',{class:'muted'}));
    return box;
  }
  historyRequest(box) {
    return {key:box.dataset.history,limit:box.historyLimit || 50,filters:Object.fromEntries(Object.entries(box.historyFilters || {}).map(([key,input])=>[key,key==='days'?Number(input.value):input.value]))};
  }
  historySettingsInfo(settings) {
    if (!settings) return;
    if (this.data) this.data.history_settings=settings;
    this.$('history-settings-info').textContent = `Conservación: ${settings.days} días · ${settings.count} registros guardados · Máximo ${settings.maximum}. ${settings.persistent ? 'Almacenamiento local de Home Assistant.' : 'Almacenamiento persistente no disponible; recarga JackSignal.'}`;
    if (!this.historyDaysDirty) this.$('history-days').value=settings.days;
  }
  async saveHistorySettings() {
    if (!this.$('history-settings-form').reportValidity()) return;
    this.$('history-save').disabled=true;
    try {
      const result=await this.request({action:'history_settings',days:Number(this.$('history-days').value)});
      this.historyDaysDirty=false;this.historySettingsInfo(result.settings);
      this.$('history-settings-message').textContent='Retención guardada. Los registros fuera del plazo se han eliminado.';
      await this.pollStatus();
    } catch(err) {this.$('history-settings-message').textContent=this.error(err);}
    finally {this.$('history-save').disabled=false;}
  }
  historyDeleteControls(scope,key,after) {
    const details=node('details');details.append(node('summary',scope==='all'?'Borrar todo el historial':'Borrar historial de este sensor'));
    details.append(node('p',scope==='all'?'Se borrarán todos los registros de todos los sensores. No cambia las reglas ni detiene el audio.':'Se borrarán todos los registros de este sensor, también los ocultos por los filtros. No cambia sus avisos.'));
    const label=node('label',null,{class:'check'}),confirm=node('input',null,{type:'checkbox'});
    const id=`history-confirm-${scope}-${this.kind}-${key || 'all'}`;confirm.id=id;label.setAttribute('for',id);label.append(confirm,node('span','Confirmo que quiero borrar estos registros. Esta acción no se puede deshacer.'));details.append(label);
    const button=node('button',scope==='all'?'Confirmar borrado completo':'Confirmar borrado del sensor',{type:'button'}),message=node('p','',{role:'status'});
    button.addEventListener('click',async()=>{
      if(!confirm.checked){message.textContent='Marca la confirmación antes de borrar.';confirm.focus();return;}
      button.disabled=true;
      try{const result=await this.request({action:'history_clear',scope,...(scope==='sensor'?{key}:{}),confirm:true});this.historySettingsInfo(result.settings);confirm.checked=false;await after();message.textContent=`Borrados ${result.removed} registros.`;}
      catch(err){message.textContent=this.error(err);}
      finally{button.disabled=false;}
    });
    details.append(button,message);return details;
  }
  renderHistory(box,items,total=items.length) {
    const list = box.querySelector('ol');list.replaceChildren();
    const names = {preparing:'Preparando',started:'Reproducción iniciada',completed:'Finalizada sin errores',interrupted:'Interrumpida',omitted:'Omitido',error:'Error'};
    for (const item of items) {
      const line = node('li',null,{class:'history-entry'});
      line.append(node('strong',names[item.status] || item.status),node('p',`${item.source} · ${labels[item.priority] || item.priority}`));
      line.append(node('time',timestampText(item.time,this._hass?.config?.time_zone),{datetime:item.time}));
      if (item.updated) line.append(node('p',`Último resultado: ${timestampText(item.updated,this._hass?.config?.time_zone)}`,{class:'muted'}));
      if (item.old != null || item.new != null) line.append(node('p',`Cambio: ${item.old ?? '—'} → ${item.new ?? '—'}`));
      line.append(node('p',item.reason));list.append(line);
    }
    const message = box.querySelector('[data-history-message]');
    const text = items.length ? `${items.length} de ${total} registros coincidentes, del más reciente al más antiguo.` : 'No hay registros que coincidan con estos filtros y la retención. Si no llegan cambios a Home Assistant, JackSignal no puede registrar un intento automático.';
    const more=box.querySelector('[data-history-more]');if(more) more.hidden=items.length>=total;
    if (message.textContent !== text) message.textContent = text;
  }
  historyCard(row) {
    const box = node('details',null,{class:'history','data-history':row.key});
    box.append(node('summary','3. Historial de avisos'));
    box.append(node('p','Historial guardado en Home Assistant según los días de conservación, con un máximo global de 1.000 registros. Los filtros se aplican a todo el historial conservado. Finalizada sin errores confirma el resultado de FFmpeg, no el sonido físico.',{class:'muted'}));
    box.historyLimit=50;box.historyFilters={};
    const filters=node('search',null,{class:'filters','aria-label':`Filtros del historial: ${row.name}`});
    const choices={status:[['all','Todos los resultados'],['preparing','Preparando'],['started','Reproducción iniciada'],['completed','Finalizada sin errores'],['interrupted','Interrumpida'],['omitted','Omitido'],['error','Error']],kind:[['all','Audio y voz'],['voice','Voz'],['audio','Audio']],priority:[['all','Todas las prioridades'],...Object.entries(labels)],days:[['0','Todo lo conservado'],['1','Últimas 24 horas'],['7','Últimos 7 días'],['30','Últimos 30 días'],['365','Último año']]};
    for(const [key,title] of [['status','Resultado'],['kind','Tipo de aviso'],['priority','Prioridad'],['days','Periodo'],['text','Buscar en origen, motivo o estado']]) {
      const field=node('div',null,{class:'field'}),id=`history-${this.kind}-${row.key}-${key}`;
      const input=node(key==='text'?'input':'select',null,{id,name:key});
      if(key==='text'){input.type='search';input.maxLength=200;}else for(const [value,label] of choices[key]) input.append(node('option',label,{value}));
      field.append(node('label',title,{for:id}),input);filters.append(field);box.historyFilters[key]=input;
      input.addEventListener('change',()=>{box.historyLimit=50;refresh();});
    }
    box.append(filters);
    const button = node('button','Actualizar historial',{type:'button','aria-label':`Actualizar historial: ${row.name}`});
    const message = node('p','',{'data-history-message':'',role:'status'});
    const refresh = async () => {
      if (button.disabled) return;
      button.disabled = true;
      try {const response = await this.request({action:'history',...this.historyRequest(box)});this.renderHistory(box,response.entries,response.total);}
      catch(err) {message.textContent = `No se pudo actualizar el historial. ${this.error(err)}`;}
      finally {button.disabled = false;}
    };
    button.addEventListener('click',refresh);
    box.addEventListener('toggle',() => {if (box.open) refresh();});
    const more=node('button','Mostrar 50 más',{type:'button','data-history-more':'',hidden:''});
    more.addEventListener('click',()=>{box.historyLimit=Math.min(1000,box.historyLimit+50);refresh();});
    box.append(button,message,node('ol',null,{class:'history-list'}),more,this.historyDeleteControls('sensor',row.key,refresh));
    return box;
  }
  selectionStatus() {
    this.$('batch-tools').hidden = !this.selected.size;
    this.$('selection-count').textContent = `${this.selected.size} avisos seleccionados (máximo 200)`;
  }
  request(payload) {return this._hass.callWS({type:'jacksignal/manage',...payload});}
  error(err) {return err?.message || 'No se pudo conectar con JackSignal. Actualiza la página e inténtalo de nuevo.';}
  setBusy(value) {
    this.busy = value; this.$('loading').hidden = !value;
    this.$('voice-defaults').disabled = value; this.$('piper-prepare').disabled = value;
    this.$('batch-edit').disabled = value; this.$('select-visible').disabled = value;
    this.$('refresh').disabled = value; this.$('stop').disabled = value;
    for (const card of this.cards.values()) card.querySelectorAll('input[type=checkbox]').forEach(input => {input.disabled = value;});
    for (const card of this.cards.values()) card.querySelectorAll('button').forEach(btn => {btn.disabled = value || btn.dataset.unavailable === 'true';});
  }
  async load() {
    if (this.busy) return;
    this.setBusy(true);
    try {this.data = await this.request({action:'list'}); this.renderList(); this.$('message').textContent = 'Configuración actualizada.';}
    catch (err) {this.$('message').textContent = this.error(err);}
    finally {this.setBusy(false);}
  }
  async perform(payload) {
    if (this.busy) return;
    this.setBusy(true);
    try {
      const result = await this.request({...payload,revision:this.data?.revision});
      if (result.rows) {this.data = result; this.renderList();}
      this.$('message').textContent = result.message || (payload.enabled ? 'Aviso activado.' : 'Aviso desactivado. Su configuración se conserva.');
    } catch (err) {this.$('message').textContent = this.error(err);}
    finally {this.setBusy(false);}
  }
  renderList() {
    if (!this.data) return;
    this.renderStatus(this.data.playback);
    this.historySettingsInfo(this.data.history_settings);
    this.$('voice-general').hidden = this.kind === 'alarm';
    const general = this.data.voice_defaults || {speed:1};
    const engineLabel = this.data.engines.find(item => item.value === general.engine)?.label;
    this.$('voice-general-info').textContent = `${engineLabel || 'Sin motor general disponible'} · ${general.language || 'Automático: preferir español'} · ${Number(general.speed).toLocaleString('es')}×. ${this.data.piper_engines?.length ? 'Piper está conectado mediante Wyoming.' : 'No se ha detectado un motor Piper conectado. Puede faltar instalarlo o añadir Wyoming.'}`;
    this.$('piper-prepare').hidden = !this.data.supervisor;
    this.$('piper-app').hidden = !this.data.supervisor;
    if (!this.data.supervisor) this.$('piper-status').textContent = 'La instalación desde aquí requiere Home Assistant OS con Supervisor. Puedes conectar un servidor Piper externo mediante Wyoming.';
    for (const [status,id] of [['configured','active'],['disabled','disabled'],['unconfigured','empty']]) this.$(`count-${id}`).textContent = this.data.rows.filter(row => row.status === status).length;
    this.selectionStatus();
    this.$('panel-info').textContent = this.data.alarm ? `Panel vinculado: ${this.data.alarm}${this.data.alarm_available ? '' : ' · No disponible'}` : 'Sin panel Alarmo vinculado. Los avisos de sensores en modo «Siempre» funcionan igualmente.';
    this.shadowRoot.querySelectorAll('[data-kind]').forEach(btn => btn.setAttribute('aria-pressed',String(btn.dataset.kind === this.kind)));
    const query = fold(this.$('query').value), filter = this.$('filter').value;
    const groups = noticeGroups(this.data.rows,this.kind,query,filter,this.kind === 'alarm' ? 'all' : this.$('availability-filter').value);
    this.$('availability-field').hidden = this.kind === 'alarm';
    this.$('results').textContent = `${groups.length} ${this.kind === 'alarm' ? (groups.length === 1 ? 'evento' : 'eventos') : (groups.length === 1 ? 'sensor' : 'sensores')}`;
    this.visibleRows = groups.slice(0,this.limit).flat();
    const visible = new Set(groups.slice(0,this.limit).map(group => `${this.kind}:${group[0].key}`));
    for (const [key,card] of this.cards) card.hidden = !visible.has(key);
    for (const group of groups.slice(0,this.limit)) {
      const cardId = `${this.kind}:${group[0].key}`;
      let card = this.cards.get(cardId);
      if (!card) {card = node('li'); this.cards.set(cardId,card); this.$('cards').append(card);}
      card.hidden = false;
      if (this.dialog.open && this.editing?.key === group[0].key) continue;
      card.replaceChildren();
      const heading = node('header'); heading.append(node('h3',group[0].name),node('span',group[0].key,{class:'muted id'}));card.append(heading);
      if (group[0].kind !== 'alarm') card.append(this.healthCard(group[0]));
      const file = group.find(row => row.kind === 'sensor'), voice = group.find(row => row.kind === 'speech');
      if (file?.configured && file.rule.enabled && voice?.configured && voice.rule.enabled && voice.rule.trigger !== 'manual' && [file.rule.on_open,file.rule.on_close].some(mode => mode !== 'never')) {
        card.append(node('p','Audio y voz pueden responder al mismo cambio. El audio de mayor prioridad puede impedir la voz. Desactiva el que no quieras usar; la prioridad de Alarmo se conserva.',{class:'warning'}));
      }
      const notices = node('div',null,{class:'notice-types'});card.append(notices);
      for (const row of group) {
      const id = `${row.kind}:${row.key}`;
      const article = node('article'); notices.append(article);
      if (row.configured) {
        const label = node('label',null,{class:'check selection',for:`select-${id}`}), check = node('input',null,{type:'checkbox',id:`select-${id}`,name:`select-${id}`});
        check.checked = this.selected.has(`${row.kind}:${row.key}`); check.disabled = this.busy;
        check.addEventListener('change', () => {if(check.checked && this.selected.size < 200) this.selected.add(`${row.kind}:${row.key}`); else {this.selected.delete(`${row.kind}:${row.key}`); check.checked=false;} this.selectionStatus();});
        label.append(check,node('span',`Seleccionar ${row.kind === 'speech' ? 'voz' : 'audio'} de ${row.name}`)); article.append(label);
      }
      article.append(node('h4',row.kind === 'sensor' ? '2. Aviso de audio' : row.kind === 'speech' ? '2. Aviso de voz' : 'Aviso de Alarmo'));
      article.append(node('span',row.kind === 'speech' && row.configured && row.rule.enabled && row.rule.trigger === 'manual' ? 'Activado · Solo manual' : ({configured:'Activado',disabled:'Desactivado',unconfigured:'Sin configurar'})[row.status],{class:'badge'}));
      if (row.kind !== 'alarm') article.append(node('p',`Ahora: ${sensorStateText(row)}`,{class:'muted','data-current-state':`${row.kind}:${row.key}`}));
      const summary = node('div',null,{class:'summary'});
      if (row.kind === 'sensor') {
        summary.append(node('p',`Al abrir: ${soundName(row.rule.sound)} · ${modes[row.rule.on_open] || 'Nunca'}`),node('p',`Al cerrar: ${soundName(row.rule.close_sound)} · ${modes[row.rule.on_close] || 'Nunca'}`));
        if (row.rule.failed_to_arm && row.rule.sound) summary.append(node('p','También avisa si impide armar Alarmo.'));
      } else if (row.kind === 'alarm') summary.append(node('p',soundName(row.rule.sound)),node('p',row.rule.repeat ? 'Repetición mientras la alarma esté disparada' : 'Sin repetición'));
      else summary.append(node('p',row.configured ? `${row.rule.before} [valor del sensor] ${row.rule.unit ? '[unidad]' : ''} ${row.rule.after}` : 'Sin frase configurada'),node('p',triggers[row.rule.trigger]));
      if (row.kind === 'speech' && Object.keys(row.rule.state_labels || {}).length) summary.append(node('p',Object.entries(row.rule.state_labels).map(([raw,spoken]) => `${raw} → ${spoken}`).join(' · ')));
      if (row.kind === 'speech' && row.configured) summary.append(node('p',row.rule.use_defaults ? 'Usa la configuración general de voz' : 'Voz personalizada para este aviso'));
      if (row.kind === 'speech' && row.configured) summary.append(node('p',`Velocidad: ${Number(row.effective?.speed ?? row.rule.speed ?? 1).toLocaleString('es')}×`));
      if (row.kind === 'speech' && row.configured) summary.append(node('p',`Intervalo mínimo: ${row.rule.cooldown} s. Los cambios dentro del intervalo se omiten.`),node('p',row.speech_status || (row.rule.trigger === 'manual' ? 'Solo manual: no habla al cambiar el sensor.' : 'Pulsa Actualizar para consultar el diagnóstico.'),{'data-speech-status':row.key,class:'tip'}));
      summary.append(node('p',`Prioridad del aviso: ${labels[row.rule.priority]}`)); article.append(summary);
      if (!this.data.alarm_available && (row.kind === 'alarm' || row.kind === 'sensor' && (row.rule.on_open === 'disarmed' || row.rule.on_close === 'disarmed' || row.rule.failed_to_arm && row.rule.sound))) article.append(node('p','Este aviso o alguna de sus condiciones necesita un panel Alarmo vinculado y disponible.',{class:'warning'}));
      if (row.kind === 'sensor' && row.configured && row.rule.on_open === 'never' && row.rule.on_close === 'never' && !row.rule.failed_to_arm) article.append(node('p','Tiene sonidos guardados, pero ninguna condición de aviso activa.',{class:'warning'}));
      const actions = node('div',null,{class:'actions'});
      const button = (text,callback,disabled=false) => {
        const btn = node('button',text,{type:'button','aria-label':`${text}: ${row.name}`});
        btn.dataset.unavailable = String(disabled); btn.disabled = this.busy || disabled; btn.addEventListener('click',callback); actions.append(btn);
      };
      const content = row.kind === 'sensor' ? 'audio' : row.kind === 'speech' ? 'voz' : 'aviso';
      button(`${row.configured ? 'Editar' : 'Configurar'} ${content}`,() => this.edit(row));
      if (row.kind === 'sensor') {
        button('Probar apertura',() => this.perform({action:'test',kind:row.kind,key:row.key,field:'sound'}),!row.rule.sound);
        button('Probar cierre',() => this.perform({action:'test',kind:row.kind,key:row.key,field:'close_sound'}),!row.rule.close_sound);
      } else button(row.kind === 'speech' ? 'Escuchar' : 'Probar',() => this.perform({action:'test',kind:row.kind,key:row.key}),!row.configured);
      button(`${row.rule.enabled ? 'Desactivar' : 'Activar'} ${content}`,() => this.perform({action:'toggle',kind:row.kind,key:row.key,enabled:!row.rule.enabled}),!row.configured);
      if (row.kind !== 'alarm') button(`Copiar ${content} a…`,() => this.copyTo(row),!row.configured);
      article.append(actions);
      }
      if (group[0].kind !== 'alarm') card.append(this.historyCard(group[0]));
    }
    this.renderHealth();
    this.$('empty').hidden = groups.length !== 0; this.$('more').hidden = groups.length <= this.limit;
  }
  field(container,key,title,value,options={}) {
    const wrapper = node('div',null,{class:options.type === 'checkbox' ? 'check' : 'field'});
    const label = node('label',title,{for:`edit-${key}`});
    let input;
    if (options.choices) {
      input = node('select',null);
      const choices = [...options.choices];
      if (value && !choices.some(item => item.value === String(value))) choices.push({value:String(value),label:`${value} (guardado; no disponible en la lista)`});
      for (const item of choices) {const opt = node('option',item.label,{value:item.value}); input.append(opt);}
    } else {input = node('input',null,{type:options.type || 'text'});}
    input.id = `edit-${key}`; input.name = key;
    if (options.type === 'checkbox') {input.checked = !!value; wrapper.append(input,label);}
    else {input.value = value ?? ''; wrapper.append(label,input);}
    for (const attr of ['min','max','step','maxlength']) if (options[attr] !== undefined) input.setAttribute(attr,String(options[attr]));
    input.required = !!options.required;
    this.controls[key] = input; container.append(wrapper); return input;
  }
  async edit(row) {
    if (this.busy) return;
    this.$('save').textContent = 'Guardar cambios';
    this.voiceToken = null; this.voiceLoading = false; this.mode = 'edit'; this.editing = row; this.editRevision = this.data.revision; this.controls = {}; this.stateLabelRows = null;
    this.$('edit-title').textContent = `${row.configured ? 'Editar' : 'Configurar'} · ${row.name}`;
    this.$('edit-help').textContent = row.kind === 'sensor' ? 'Apertura y cierre necesitan su propio sonido. Puedes elegir el mismo para ambos. Los cambios solo se aplican al guardar.' : 'Los cambios solo se aplican al guardar. Desactivar conserva la configuración.';
    this.$('fields').replaceChildren(); this.$('form-error').textContent = '';
    this.dialog.showModal(); this.$('edit-title').focus(); this.$('save').disabled = true;
    try {
      const media = row.kind === 'speech' ? {items:[]} : await this.request({action:'media'});
      if (!this.dialog.open || this.editing !== row) return;
      const root = this.$('fields'), rule = row.kind === 'speech' && row.rule.use_defaults ? {...row.rule,...this.data.voice_defaults} : row.rule;
      if (media.truncated) root.append(node('p','La lista de archivos está limitada. Los archivos ya asignados se conservan. Usa los formularios de configuración para explorar el resto.',{class:'warning'}));
      if (row.kind !== 'speech' && !media.items.length) root.append(node('p','No hay archivos de audio en Mis medios. Súbelos desde Configuración y audio → Enviar audio.',{class:'warning'}));
      const choices = [{value:'',label:'Sin sonido'},...media.items];
      const selectSound = (container,key,title) => this.field(container,key,title,rule[key]?.media_content_id || '',{choices});
      this.field(root,'enabled','Aviso activado',rule.enabled,{type:'checkbox'});
      if (row.kind === 'sensor') {
        for (const [title,sound,mode] of [['Apertura / activación','sound','on_open'],['Cierre / desactivación','close_sound','on_close']]) {
          const group = node('fieldset',null); group.append(node('legend',title));
          selectSound(group,sound,'Sonido'); this.field(group,mode,'Cuándo avisar',rule[mode],{choices:Object.entries(modes).map(([value,label]) => ({value,label}))}); root.append(group);
        }
        this.field(root,'failed_to_arm','Avisar si este sensor impide armar Alarmo (usa el sonido de apertura)',rule.failed_to_arm,{type:'checkbox'});
        const advanced = node('details',null); advanced.append(node('summary','Opciones avanzadas del sensor'));
        advanced.append(node('p',`Estado interno actual: ${row.state ?? 'No disponible'}. Revisa la polaridad si los avisos se invierten.`));
        this.field(advanced,'open_state','Estado al abrir / activarse (obligatorio)',rule.open_state,{required:true,maxlength:100});
        this.field(advanced,'closed_state','Estado al cerrar / desactivarse (obligatorio)',rule.closed_state,{required:true,maxlength:100});root.append(advanced);
      } else if (row.kind === 'alarm') {
        selectSound(root,'sound','Sonido (obligatorio)'); this.controls.sound.required = true;
        if (row.key === 'triggered') this.field(root,'repeat','Repetir mientras la alarma esté disparada',rule.repeat,{type:'checkbox'});
      } else {
        const inherit = this.field(root,'use_defaults','Usar motor, idioma, voz y velocidad generales',!!rule.use_defaults,{type:'checkbox'});
        const engine = this.field(root,'engine','Motor de voz (obligatorio)',rule.engine,{choices:[{value:'',label:'Selecciona un motor de voz'},...this.data.engines],required:true});
        if (!this.data.engines.length) root.append(node('p','Configura antes una integración de texto a voz en Home Assistant.',{class:'warning'}));
        const language = this.field(root,'language','Idioma',rule.language || '',{choices:[{value:'',label:'Automático · Preferir español'}]});
        this.field(root,'voice','Voz',rule.voice || '',{choices:[{value:'',label:'Automática para el idioma'}]});
        const voiceHelp = node('p','', {class:'tip'}); root.append(voiceHelp); this.voiceHelp = voiceHelp;
        engine.addEventListener('change', () => this.loadVoices(true));
        language.addEventListener('change', () => this.loadVoices(false, true));
        root.append(node('p','¿Quieres voz local? Instala Piper, elige una voz española y añade su integración Wyoming. Después actualiza este panel. Solo aparecen motores configurados en Home Assistant.',{class:'muted'}));
        const speed = this.field(root,'speed','Velocidad de voz (obligatoria)',rule.speed ?? 1,{type:'number',min:0.5,max:2,step:0.05,required:true});
        const updateInheritance = () => {
          if (inherit.checked) {
            const defaults = this.data.voice_defaults || {};
            this.fillChoices(engine,[{value:'',label:'Sin motor general'},...this.data.engines],defaults.engine || '');
            this.fillChoices(language,[{value:'',label:'Automático · Preferir español'}],defaults.language || '');
            this.fillChoices(this.controls.voice,[{value:'',label:'Automática para el idioma'}],defaults.voice || '');
            speed.value = defaults.speed ?? 1;
          }
          for (const key of ['engine','language','voice','speed']) this.controls[key].disabled = inherit.checked;
          this.loadVoices(false);
        };
        inherit.addEventListener('change',updateInheritance); updateInheritance();
        speed.setAttribute('aria-describedby','speed-help');
        root.append(node('p','De 0,5× a 2×. 0,8× más lento · 1× normal · 1,2× más rápido. Conserva el tono. Se aplica sobre la velocidad configurada en Piper o en tu motor de voz.',{id:'speed-help',class:'muted'}));
        this.field(root,'before','Texto antes del valor',rule.before,{maxlength:1000});
        this.field(root,'after','Texto después del valor',rule.after,{maxlength:1000});
        this.field(root,'unit','Añadir la unidad del sensor',rule.unit,{type:'checkbox'});
        const trigger = this.field(root,'trigger','Cuándo hablar',rule.trigger,{choices:Object.entries(triggers).map(([value,label]) => ({value,label}))});
        const automaticHelp = node('p','',{class:'warning'}); root.append(automaticHelp);
        const explainTrigger = () => {automaticHelp.textContent = trigger.value === 'manual'
          ? 'Solo manual: activar el aviso NO hace que hable al cambiar el sensor. Elige Cada cambio de valor o un umbral para avisos automáticos.'
          : 'Aviso automático: se reproducirá al cumplir esta condición, si está activado y la prioridad lo permite. La prueba manual no comprueba el disparador ni el intervalo.';};
        trigger.addEventListener('change',explainTrigger); explainTrigger();
        const threshold = this.field(root,'threshold','Umbral numérico',rule.threshold,{type:'number',step:'any'});
        const updateThreshold = () => {const needed = ['above','below'].includes(trigger.value); threshold.required = needed; threshold.parentElement.hidden = !needed;};
        trigger.addEventListener('change',updateThreshold); updateThreshold();
        this.field(root,'cooldown','Intervalo mínimo entre avisos (segundos)',rule.cooldown,{type:'number',min:0,max:86400,step:1,required:true});
        root.append(node('p','El intervalo omite cambios durante ese tiempo; no los retrasa ni los pone en cola. Usa 0 para avisar tanto al abrir como al cerrar sin espera.',{class:'tip'}));
        const phrase = node('p','',{class:'tip phrase'}); root.append(phrase);
        const updatePhrase = () => {const r = this.collectRule(); phrase.textContent = 'Dirá: ' + [r.before,Object.hasOwn(r.state_labels || {},row.state) ? r.state_labels[row.state] : row.state ?? '[sensor no disponible]',r.unit ? row.unit : '',r.after].filter(Boolean).join(' ');};
        for (const key of ['before','after','unit']) this.controls[key].addEventListener('input',updatePhrase);
        this.editStateLabels(root,rule,row,updatePhrase);
        updatePhrase();
        const preview = node('button','Escuchar antes de guardar (P0)',{type:'button'});
        preview.addEventListener('click',async () => {
          if (!this.$('editor').reportValidity() || this.voiceLoading || this.saving) return;
          preview.disabled = true;
          try {const result = await this.request({action:'test',kind:'speech',key:row.key,rule:this.collectRule()}); this.$('form-error').textContent = result.message;}
          catch(err) {this.$('form-error').textContent = this.error(err);}
          finally {preview.disabled = false;}
        }); const previewActions = node('div',null,{class:'actions'}); previewActions.append(preview); root.append(previewActions);
        const stop = node('button','Detener prueba de voz',{type:'button'});
        stop.addEventListener('click',async () => {try {this.$('form-error').textContent = (await this.request({action:'stop_test'})).message;} catch(err) {this.$('form-error').textContent=this.error(err);}}); previewActions.append(stop);
        this.loadVoices(false);

      }
      this.field(root,'priority','Prioridad del aviso',rule.priority,{choices:Object.entries(labels).map(([value,label]) => ({value,label}))});
      this.$('save').disabled = false;
    } catch (err) {this.$('form-error').textContent = this.error(err);}
  }
  editDefaults() {
    if (this.busy) return;
    this.simpleEditor('defaults','Voz predeterminada','Los nuevos avisos heredarán estos valores. Los existentes conservarán sus ajustes salvo que marques «Aplicar a todos». Cada aviso puede personalizarse después.');
    const root = this.$('fields'), rule = this.data.voice_defaults || {};
    const engine = this.field(root,'engine','Motor general (obligatorio)',rule.engine,{choices:[{value:'',label:'Selecciona Piper u otro motor'},...this.data.engines],required:true});
    const language = this.field(root,'language','Idioma',rule.language || '',{choices:[{value:'',label:'Automático · Preferir español'}]});
    this.field(root,'voice','Voz',rule.voice || '',{choices:[{value:'',label:'Automática para el idioma'}]});
    this.voiceHelp = node('p','',{class:'tip'}); root.append(this.voiceHelp);
    this.field(root,'speed','Velocidad general (obligatoria)',rule.speed ?? 1,{type:'number',min:0.5,max:2,step:0.05,required:true});
    root.append(node('p','0,8× más lento · 1× normal · 1,2× más rápido. La prioridad de cada aviso se conserva.'));
    this.field(root,'apply_to_all','Aplicar estos valores a todos los avisos de voz existentes',false,{type:'checkbox'});
    engine.addEventListener('change',() => this.loadVoices(true));
    language.addEventListener('change',() => this.loadVoices(false,true));
    this.loadVoices(); engine.focus();
  }
  preparePiper() {
    if (this.busy || !this.data.supervisor) return;
    this.simpleEditor('install','Preparar Piper local','Se comprobará si la aplicación oficial Piper está instalada. Si falta, se descargará, se configurará es_ES-davefx-medium y el inicio automático, y se iniciará. Necesita Internet y espacio libre; puede tardar varios minutos. Mantén esta pantalla abierta. Si ya existe, se conserva su configuración y se inicia si está detenida. Después debes completar Wyoming en Dispositivos y servicios.');
    this.field(this.$('fields'),'consent','Entiendo los cambios y quiero preparar Piper (obligatorio)',false,{type:'checkbox',required:true});
    this.$('save').textContent = 'Preparar Piper'; this.controls.consent.focus();
  }
  async installPiper() {
    if (!this.data.supervisor || !this.controls.consent.checked) return;
    this.saving = true; this.$('save').disabled = true; this.$('cancel').disabled = true;
    const guard = event => event.preventDefault(); this.dialog.addEventListener('cancel',guard);
    const status = text => {this.$('form-error').textContent = text;};
    const api = (endpoint, method='get',data={}) => this._hass.callWS({type:'supervisor/api',endpoint,method,data,timeout:600});
    try {
      status('Comprobando la aplicación Piper…');
      const installed = await api('/addons');
      if (!Array.isArray(installed.addons)) throw new Error('No se pudo consultar la lista de aplicaciones.');
      const existing = installed.addons.some(app => app.slug === 'core_piper');
      if (!existing) {
        status('Instalando Piper. Puede tardar varios minutos…');
        await api('/addons/core_piper/install','post');
        const info = await api('/addons/core_piper/info');
        const options = {...info.options,voice:'es_ES-davefx-medium'};
        if ('backend' in options) options.backend = 'piper';
        await api('/addons/core_piper/options','post',{options,boot:'auto'});
      }
      const info = await api('/addons/core_piper/info');
      if (info.state !== 'started') {status('Iniciando Piper y preparando la voz…'); await api('/addons/core_piper/start','post');}
      const finalInfo = await api('/addons/core_piper/info');
      if (finalInfo.state !== 'started') throw new Error('Piper todavía no está iniciado. Revisa su aplicación y registros.');
      const message = existing ? 'Piper ya estaba instalado; su configuración se conserva. Completa Wyoming si falta y pulsa Actualizar.' : 'Piper instalado e iniciado con voz española. Ahora añade Wyoming en Dispositivos y servicios y pulsa Actualizar.';
      this.$('piper-status').textContent = message; status(message);
    } catch (err) {
      status(`No se ha completado la preparación. ${this.error(err)} Revisa Piper desde «Abrir Piper» antes de reintentar; la instalación puede haber quedado parcialmente completada.`);
    } finally {
      this.saving = false; this.$('save').disabled = false; this.$('cancel').disabled = false;
      this.dialog.removeEventListener('cancel',guard);
    }
  }
  fillChoices(input, choices, value) {
    input.replaceChildren();
    if (value && !choices.some(item => item.value === value)) choices.push({value,label:`${value} (guardado; no disponible)`});
    for (const item of choices) input.append(node('option',item.label,{value:item.value}));
    input.value = value || '';
  }
  async loadVoices(resetEngine=false,resetVoice=false) {
    const controls = this.controls, token = Symbol(); this.voiceToken = token; this.voiceLoading = true;
    if (resetEngine) controls.language.value = '';
    if (resetEngine || resetVoice) controls.voice.value = '';
    const engine = controls.engine.value;
    try {
      if (!engine) {this.voiceHelp.textContent = 'Selecciona un motor para consultar sus idiomas y voces.'; return;}
      const info = await this.request({action:'tts_info',engine,language:controls.language.value,voice:controls.voice.value});
      if (this.voiceToken !== token || this.controls !== controls || !this.dialog.open) return;
      const languageName = value => {try {return new Intl.DisplayNames(['es'],{type:'language'}).of(value.replaceAll('_','-')) + ` (${value})`;} catch {return value;}};
      this.fillChoices(controls.language,[{value:'',label:`Automático: ${languageName(controls.language.value ? info.default_language : info.language)}`},...info.languages.map(value => ({value,label:languageName(value)}))],controls.language.value);
      // The backend also resolves an automatic voice matching the effective language.
      const voice = controls.voice.value || '';
      this.fillChoices(controls.voice,[{value:'',label:'Automática para el idioma'},...info.voices],voice);
      this.voiceHelp.textContent = `Idioma efectivo: ${languageName(info.language)}. Automático prefiere español de España cuando está disponible. ${info.voices.length ? 'Elige una voz del idioma seleccionado.' : 'Este motor no ofrece voces seleccionables.'}`;
    } catch(err) {if (this.voiceToken === token) this.voiceHelp.textContent = this.error(err);}
    finally {if(this.voiceToken === token) this.voiceLoading = false;}
  }
  simpleEditor(mode,title,help) {
    this.$('save').textContent = mode === 'copy' ? 'Revisar copia' : 'Guardar cambios';
    this.voiceToken = null; this.voiceLoading = false; this.mode = mode; this.controls = {}; this.editRevision = this.data.revision;
    this.$('edit-title').textContent = title; this.$('edit-help').textContent = help;
    this.$('fields').replaceChildren(); this.$('form-error').textContent = ''; this.$('save').disabled = false;
    this.dialog.showModal();
  }
  editBatch() {
    if(this.busy || !this.selected.size) return;
    this.batchTargets = this.data.rows.filter(row => this.selected.has(`${row.kind}:${row.key}`)).map(({kind,key}) => ({kind,key}));
    this.simpleEditor('batch',`Modificar ${this.selected.size} avisos`,'Los sonidos y condiciones se conservan. Se aplicará todo junto al guardar. Cambiar la activación de la sirena afecta a una alarma que esté disparada.');
    this.$('fields').append(node('p',this.data.rows.filter(row => this.selected.has(`${row.kind}:${row.key}`)).map(row => `${row.name} (${row.kind === 'speech' ? 'voz' : 'audio'})`).join(' · ')));
    this.field(this.$('fields'),'enabled','Activación','',{choices:[{value:'',label:'Conservar'},{value:'true',label:'Activar'},{value:'false',label:'Desactivar'}]});
    this.field(this.$('fields'),'priority','Prioridad','',{choices:[{value:'',label:'Conservar'},...Object.entries(labels).map(([value,label]) => ({value,label}))]});
    this.controls.enabled.focus();
  }
  copyTo(row) {
    this.editing = row;
    this.simpleEditor('copy',`Copiar ${row.name}`,'Elige el destino. Después podrás revisar todos los campos antes de guardar y reemplazar su configuración. La copia comienza desactivada y conserva los estados de apertura/cierre del destino.');
    const targets = this.data.rows.filter(item => item.kind === row.kind && item.key !== row.key);
    this.field(this.$('fields'),'target','Sensor de destino (obligatorio)','',{choices:[{value:'',label:'Selecciona el destino'},...targets.map(item => ({value:item.key,label:`${item.name} · ${item.configured ? 'reemplazará su aviso' : 'sin configurar'}`}))],required:true});
    this.controls.target.focus();
  }
  editStateLabels(root,rule,row,updatePhrase) {
    const group = node('fieldset'); group.append(node('legend','Qué dice cada estado'));
    group.append(node('p',`Estado interno actual: ${row.state ?? 'No disponible'}. Escribe el estado exacto que detecta Home Assistant y las palabras que quieres oír.`,{class:'muted'}));
    group.append(node('p','Ejemplos: on → abierta y off → cerrada; o on → encendido y off → apagado. También puedes usar true/false, open/closed u otros estados. No cambia cuándo se activa el aviso. Sin equivalencia, se lee el valor original.',{class:'tip'}));
    const list = node('div'); group.append(list); this.stateLabelRows = [];
    const add = node('button','Añadir equivalencia',{type:'button'});
    let nextId = 0;
    const validate = () => {
      for (const item of this.stateLabelRows) {
        const duplicate = this.stateLabelRows.some(other => other !== item && other.raw.value === item.raw.value);
        item.raw.setCustomValidity(duplicate ? 'Este estado ya tiene una equivalencia. Usa una sola fila por estado.' : item.raw.value && !item.raw.value.trim() ? 'Escribe un estado válido.' : '');
        item.spoken.setCustomValidity(item.spoken.value && !item.spoken.value.trim() ? 'Escribe las palabras que debe decir.' : '');
      }
    };
    const append = (value='',text='',focus=false) => {
      if (this.stateLabelRows.length >= 32) return;
      const box = node('fieldset'); box.append(node('legend','Equivalencia de voz'));
      const inputs = [];
      for (const [suffix,title,current,limit] of [['state','Cuando detecte (obligatorio)',value,100],['spoken','Decir (obligatorio)',text,200]]) {
        const id = `voice-map-${nextId}-${suffix}`, wrapper = node('div',null,{class:'field'});
        const input = node('input',null,{id,name:id,type:'text',maxlength:String(limit),required:''}); input.value = current;
        if (suffix === 'state') {input.autocapitalize = 'none'; input.spellcheck = false; input.setAttribute('autocorrect','off');}
        wrapper.append(node('label',title,{for:id}),input); box.append(wrapper); inputs.push(input);
      }
      nextId++;
      const item = {raw:inputs[0],spoken:inputs[1]}; this.stateLabelRows.push(item);
      for (const input of inputs) input.addEventListener('input',() => {validate();updatePhrase();});
      const remove = node('button','Eliminar equivalencia',{type:'button'});
      remove.addEventListener('click',() => {this.stateLabelRows = this.stateLabelRows.filter(other => other !== item);box.remove();add.disabled = false;validate();updatePhrase();add.focus();});
      box.append(remove); list.append(box); add.disabled = this.stateLabelRows.length >= 32;
      if (focus) item.raw.focus();
    };
    add.addEventListener('click',() => append('','',true)); group.append(add); root.append(group);
    const suggestions = row.suggested_state_labels || {};
    const proposed = !Object.hasOwn(rule,'state_labels') && Object.keys(suggestions).length > 0;
    const help = node('p',proposed
      ? 'Propuesta automática según el tipo de sensor. Revisa las palabras, cámbialas o elimina las equivalencias que no quieras. Solo se aplicarán al guardar.'
      : Object.keys(suggestions).length
        ? 'Se conservan tus equivalencias, incluso si las dejaste vacías. Puedes añadir las sugerencias que falten sin reemplazar tus textos.'
        : 'No hay una propuesta automática para este tipo de sensor. Puedes añadir tus equivalencias manualmente.',{class:'tip'});
    group.insertBefore(help,list);
    for (const [raw,spoken] of Object.entries(proposed ? suggestions : rule.state_labels || {})) append(raw,spoken);
    if (Object.keys(suggestions).length) {
      const suggest = node('button','Añadir sugerencias que faltan',{type:'button'});
      suggest.addEventListener('click',() => {
        for (const [raw,spoken] of Object.entries(suggestions)) {
          if (!this.stateLabelRows.some(item => item.raw.value === raw)) append(raw,spoken);
        }
        validate();updatePhrase();
      });
      group.append(suggest);
    }
  }
  collectRule() {
    const rule = {...this.editing.rule};
    for (const [key,input] of Object.entries(this.controls)) {
      if (['sound','close_sound'].includes(key)) {if (input.value) rule[key] = {media_content_id:input.value,media_content_type:'music'}; else delete rule[key];}
      else if (input.type === 'checkbox') rule[key] = input.checked;
      else if (input.type === 'number') {if (input.value === '') delete rule[key]; else rule[key] = Number(input.value);}
      else rule[key] = input.value;
    }
    if (this.editing.kind === 'speech' && this.stateLabelRows) {
      rule.state_labels = Object.fromEntries(this.stateLabelRows.map(({raw,spoken}) => [raw.value,spoken.value.trim()]));
    }
    return rule;
  }
  async save() {
    if (this.saving || this.$('save').disabled || this.voiceLoading) return;
    if (this.mode === 'install') {await this.installPiper(); return;}
    if (this.mode === 'copy') {
      const target = this.data.rows.find(row => row.kind === this.editing.kind && row.key === this.controls.target.value);
      if (!target) return;
      const rule = {...this.editing.rule,enabled:false};
      if (target.kind === 'sensor') {rule.open_state = target.rule.open_state; rule.closed_state = target.rule.closed_state;}
      this.dialog.close(); this.edit({...target,rule}); return;
    }
    const rule = this.mode === 'batch' ? null : this.mode === 'defaults' ? Object.fromEntries(['engine','language','voice','speed'].map(key => [key,key === 'speed' ? Number(this.controls[key].value) : this.controls[key].value])) : this.collectRule();
    const changes = {};
    if (this.mode === 'batch') {
      if (this.controls.enabled.value) changes.enabled = this.controls.enabled.value === 'true';
      if (this.controls.priority.value) changes.priority = this.controls.priority.value;
      if (!Object.keys(changes).length) {this.$('form-error').textContent = 'Elige al menos un cambio.'; this.$('form-error').focus(); return;}
    }
    this.saving = true; this.$('save').disabled = true; this.$('cancel').disabled = true;
    const guard = e => e.preventDefault(); this.dialog.addEventListener('cancel',guard);
    try {
      this.data = await this.request(this.mode === 'defaults' ? {action:'defaults',rule,apply_to_all:this.controls.apply_to_all.checked,revision:this.editRevision} : this.mode === 'batch' ? {action:'batch',targets:this.batchTargets,changes,revision:this.editRevision} : {action:'save',kind:this.editing.kind,key:this.editing.key,revision:this.editRevision,rule});
      this.selected.clear();
      this.dialog.close(); this.renderList(); this.$('results').focus(); this.$('message').textContent = 'Cambios guardados.';
    } catch (err) {this.$('form-error').textContent = this.error(err); this.$('form-error').focus();}
    finally {this.saving = false;this.$('save').disabled = false;this.$('cancel').disabled = false;this.dialog.removeEventListener('cancel',guard);}
  }
}
if (!customElements.get('jacksignal-panel')) customElements.define('jacksignal-panel',JackSignalPanel);
