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
class JackSignalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this.kind = 'sensor'; this.limit = 60; this.cards = new Map(); this.busy = false;
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#17212b);background:var(--primary-background-color,#f5f7fa);font:16px/1.5 var(--paper-font-body1_-_font-family,system-ui)}
        *{box-sizing:border-box} [hidden]{display:none!important}
        header{display:flex;align-items:center;gap:12px;padding:16px 24px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#d5dae0)}
        h1{font-size:1.6rem;margin:0}h2{font-size:1.15rem;margin:0}p{margin:.5rem 0}main{max-width:1160px;margin:auto;padding:24px}
        .muted{color:var(--secondary-text-color,#526171)}.tools,.actions,.nav{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.tools{justify-content:space-between;margin-bottom:20px}
        a{color:var(--primary-color,#006a96)}button,input,select{font:inherit;font-size:max(1rem,1em);color:inherit}button,a.button{min-height:48px;padding:10px 16px;border:1px solid var(--divider-color,#9ca9b5);border-radius:9px;background:var(--card-background-color,#fff);cursor:pointer;text-decoration:none}
        button:hover:not(:disabled){border-color:var(--primary-color,#00789a)}button[aria-pressed=true],button.primary{background:var(--primary-color,#00789a);color:var(--text-primary-color,#fff);border-color:transparent}
        button:disabled{opacity:.55;cursor:default} :focus-visible{outline:3px solid var(--primary-color,#00789a);outline-offset:3px}
        search{display:block;margin:20px 0} .filters{display:flex;flex-wrap:wrap;gap:16px;align-items:end}.field{display:flex;flex-direction:column;gap:5px;margin-bottom:14px;min-width:0}.filters .field{flex:1;min-width:190px;margin:0}
        input:not([type=checkbox]),select{width:100%;min-height:48px;padding:10px;border:1px solid var(--secondary-text-color,#64717f);border-radius:8px;background:var(--card-background-color,#fff)}
        .check{display:flex;align-items:center;gap:10px;min-height:48px;margin:8px 0}input[type=checkbox]{width:22px;height:22px;accent-color:var(--primary-color,#00789a)}
        #cards{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:16px}li{min-width:0}article{height:100%;padding:20px;border:1px solid var(--divider-color,#d5dae0);border-radius:14px;background:var(--card-background-color,#fff);overflow-wrap:anywhere}
        .badge{display:inline-block;font-size:.85rem;border:1px solid var(--divider-color,#b7c1cb);border-radius:20px;padding:3px 10px;margin:8px 0}.summary{min-height:75px}.warning{border-inline-start:3px solid var(--warning-color,#a56b00);padding-inline-start:10px;font-size:.9rem}.actions{margin-top:16px}
        #message{min-height:30px;padding:6px 0}.empty{padding:32px;text-align:center;border:1px dashed var(--divider-color,#b0bac4);border-radius:12px}
        dialog{width:min(620px,calc(100% - 24px));max-height:90dvh;padding:24px;border:1px solid var(--divider-color,#b0bac4);border-radius:16px;color:var(--primary-text-color,#17212b);background:var(--card-background-color,#fff)}
        dialog:modal{overscroll-behavior:contain}dialog::backdrop{background:#0008;overflow:hidden;overscroll-behavior:contain}
        fieldset{border:1px solid var(--divider-color,#b0bac4);border-radius:10px;padding:16px;margin:16px 0;min-width:0}legend{font-weight:600}details{margin:14px 0}summary{cursor:pointer;min-height:48px;padding:10px 0}
        #form-error{color:var(--error-color,#b3261e);min-height:24px}progress{width:100%}.id{font-size:.8rem;overflow-wrap:anywhere}.tip{padding:12px;border-radius:8px;background:var(--secondary-background-color,#eef2f5)}
        @media(max-width:600px){main{padding:16px}header{padding:12px}h1{font-size:1.3rem}.actions button{flex:1}dialog{padding:18px}}
      </style>
      <header lang="es"><ha-menu-button></ha-menu-button><div><h1>Gestionar avisos</h1><span class="muted">JackSignal · Audio con prioridades</span></div></header>
      <main lang="es">
        <div class="tools"><p id="panel-info" class="muted">Cargando configuración…</p><div class="actions"><a class="button" href="/config/integrations/integration/jacksignal">Configuración y audio</a><button id="refresh" type="button">Actualizar</button></div></div>
        <div class="nav" role="group" aria-label="Tipo de aviso"><button type="button" data-kind="sensor" aria-pressed="true">Sensores</button><button type="button" data-kind="alarm" aria-pressed="false">Alarmo</button><button type="button" data-kind="speech" aria-pressed="false">Voz</button></div>
        <search aria-label="Buscar avisos"><div class="filters"><div class="field"><label for="query">Buscar por nombre, sensor o sonido</label><input id="query" type="search" name="query" placeholder="Por ejemplo, ventana del salón" autocapitalize="none" spellcheck="false"></div><div class="field"><label for="filter">Mostrar</label><select id="filter" name="filter"><option value="all">Todos</option><option value="configured">Configurados y activados</option><option value="unconfigured">Sin configurar</option><option value="disabled">Desactivados</option></select></div></div></search>
        <p class="tip">Las pruebas son manuales, usan prioridad baja (P0) y no repiten el sonido. No activan Alarmo ni modifican el sensor. Puedes probar una regla desactivada sin activarla.</p>
        <button id="stop" type="button">Detener prueba</button><p id="message" role="status" aria-live="polite"></p><progress id="loading" aria-label="Cargando avisos"></progress>
        <h2 id="results" tabindex="-1">Avisos</h2><ul id="cards" role="list"></ul><p id="empty" class="empty" hidden>No hay avisos que coincidan. Cambia la búsqueda o el filtro.</p><button id="more" type="button" hidden>Mostrar más</button>
      </main>
      <dialog lang="es" aria-labelledby="edit-title"><h2 id="edit-title">Editar aviso</h2><p id="edit-help" class="muted"></p><form id="editor" aria-labelledby="edit-title"><div id="fields"></div><p id="form-error" role="status" aria-live="polite" tabindex="-1"></p><div class="actions"><button id="save" class="primary" type="submit">Guardar cambios</button><button id="cancel" type="button">Cancelar</button></div></form></dialog>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.shadowRoot.querySelectorAll('[data-kind]').forEach(btn => btn.addEventListener('click', () => {
      this.kind = btn.dataset.kind; this.limit = 60; this.renderList();
    }));
    this.$('query').addEventListener('input', () => {this.limit = 60; this.renderList();});
    this.$('filter').addEventListener('change', () => {this.limit = 60; this.renderList();});
    this.$('refresh').addEventListener('click', () => this.load());
    this.$('more').addEventListener('click', () => {this.limit += 60; this.renderList();});
    this.$('stop').addEventListener('click', () => this.perform({action:'stop_test'}));
    this.$('cancel').addEventListener('click', () => this.dialog.close());
    this.$('editor').addEventListener('submit', e => {e.preventDefault(); this.save();});
    this.dialog = this.shadowRoot.querySelector('dialog');
  }
  set hass(value) {
    this._hass = value;
    this.shadowRoot.querySelector('ha-menu-button').hass = value;
    if (this.isConnected && !this.data && !this.busy) this.load();
  }
  set narrow(value) {this.shadowRoot.querySelector('ha-menu-button').narrow = value;}
  connectedCallback() {if (this._hass && !this.data) this.load();}
  request(payload) {return this._hass.callWS({type:'jacksignal/manage',...payload});}
  error(err) {return err?.message || 'No se pudo conectar con JackSignal. Actualiza la página e inténtalo de nuevo.';}
  setBusy(value) {
    this.busy = value; this.$('loading').hidden = !value;
    this.$('refresh').disabled = value; this.$('stop').disabled = value;
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
    this.$('panel-info').textContent = this.data.alarm ? `Panel vinculado: ${this.data.alarm}${this.data.alarm_available ? '' : ' · No disponible'}` : 'Sin panel Alarmo vinculado. Los avisos de sensores en modo «Siempre» funcionan igualmente.';
    this.shadowRoot.querySelectorAll('[data-kind]').forEach(btn => btn.setAttribute('aria-pressed',String(btn.dataset.kind === this.kind)));
    const query = fold(this.$('query').value), filter = this.$('filter').value;
    const rows = this.data.rows.filter(row => row.kind === this.kind && (filter === 'all' || row.status === filter) && fold([row.name,row.key,soundName(row.rule.sound),soundName(row.rule.close_sound),row.rule.before,row.rule.after].join(' ')).includes(query));
    this.$('results').textContent = `${rows.length} ${rows.length === 1 ? 'aviso' : 'avisos'}`;
    const visible = new Set(rows.slice(0,this.limit).map(row => `${row.kind}:${row.key}`));
    for (const [key,card] of this.cards) card.hidden = !visible.has(key);
    for (const row of rows.slice(0,this.limit)) {
      const id = `${row.kind}:${row.key}`;
      let card = this.cards.get(id);
      if (!card) {
        card = node('li',null); card.append(node('article',null));
        this.cards.set(id,card); this.$('cards').append(card);
      }
      card.hidden = false;
      // Keep the invoker button attached while a native dialog is open.
      if (this.dialog.open && this.editing?.key === row.key && this.editing.kind === row.kind) continue;
      const article = card.firstChild; article.replaceChildren();
      article.append(node('h2',row.name),node('div',row.key,{class:'muted id'}));
      article.append(node('span',({configured:'Activado',disabled:'Desactivado',unconfigured:'Sin configurar'})[row.status],{class:'badge'}));
      if (row.kind !== 'alarm') {
        let state = row.state ?? 'No disponible';
        if (row.kind === 'sensor') state = row.state?.toLowerCase() === row.rule.open_state ? 'Abierto / activado' : row.state?.toLowerCase() === row.rule.closed_state ? 'Cerrado / desactivado' : state;
        article.append(node('p',`Ahora: ${state}`,{class:'muted'}));
      }
      const summary = node('div',null,{class:'summary'});
      if (row.kind === 'sensor') {
        summary.append(node('p',`Al abrir: ${soundName(row.rule.sound)} · ${modes[row.rule.on_open] || 'Nunca'}`),node('p',`Al cerrar: ${soundName(row.rule.close_sound)} · ${modes[row.rule.on_close] || 'Nunca'}`));
        if (row.rule.failed_to_arm && row.rule.sound) summary.append(node('p','También avisa si impide armar Alarmo.'));
      } else if (row.kind === 'alarm') summary.append(node('p',soundName(row.rule.sound)),node('p',row.rule.repeat ? 'Repetición mientras la alarma esté disparada' : 'Sin repetición'));
      else summary.append(node('p',row.configured ? `${row.rule.before} [valor del sensor] ${row.rule.unit ? '[unidad]' : ''} ${row.rule.after}` : 'Sin frase configurada'),node('p',triggers[row.rule.trigger]));
      summary.append(node('p',`Prioridad del aviso: ${labels[row.rule.priority]}`)); article.append(summary);
      if (!this.data.alarm_available && (row.kind === 'alarm' || row.kind === 'sensor' && (row.rule.on_open === 'disarmed' || row.rule.on_close === 'disarmed' || row.rule.failed_to_arm && row.rule.sound))) article.append(node('p','Este aviso o alguna de sus condiciones necesita un panel Alarmo vinculado y disponible.',{class:'warning'}));
      if (row.kind === 'sensor' && row.configured && row.rule.on_open === 'never' && row.rule.on_close === 'never' && !row.rule.failed_to_arm) article.append(node('p','Tiene sonidos guardados, pero ninguna condición de aviso activa.',{class:'warning'}));
      const actions = node('div',null,{class:'actions'});
      const button = (text,callback,disabled=false) => {
        const btn = node('button',text,{type:'button','aria-label':`${text}: ${row.name}`});
        btn.dataset.unavailable = String(disabled); btn.disabled = this.busy || disabled; btn.addEventListener('click',callback); actions.append(btn);
      };
      button(row.configured ? 'Editar' : 'Configurar',() => this.edit(row));
      if (row.kind === 'sensor') {
        button('Probar apertura',() => this.perform({action:'test',kind:row.kind,key:row.key,field:'sound'}),!row.rule.sound);
        button('Probar cierre',() => this.perform({action:'test',kind:row.kind,key:row.key,field:'close_sound'}),!row.rule.close_sound);
      } else button(row.kind === 'speech' ? 'Escuchar' : 'Probar',() => this.perform({action:'test',kind:row.kind,key:row.key}),!row.configured);
      button(row.rule.enabled ? 'Desactivar' : 'Activar',() => this.perform({action:'toggle',kind:row.kind,key:row.key,enabled:!row.rule.enabled}),!row.configured);
      article.append(actions);
    }
    this.$('empty').hidden = rows.length !== 0; this.$('more').hidden = rows.length <= this.limit;
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
    this.editing = row; this.editRevision = this.data.revision; this.controls = {};
    this.$('edit-title').textContent = `${row.configured ? 'Editar' : 'Configurar'} · ${row.name}`;
    this.$('edit-help').textContent = row.kind === 'sensor' ? 'Apertura y cierre necesitan su propio sonido. Puedes elegir el mismo para ambos. Los cambios solo se aplican al guardar.' : 'Los cambios solo se aplican al guardar. Desactivar conserva la configuración.';
    this.$('fields').replaceChildren(); this.$('form-error').textContent = '';
    this.dialog.showModal(); this.$('cancel').focus(); this.$('save').disabled = true;
    try {
      const media = row.kind === 'speech' ? {items:[]} : await this.request({action:'media'});
      if (!this.dialog.open || this.editing !== row) return;
      const root = this.$('fields'), rule = row.rule;
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
        this.field(root,'engine','Motor de voz (obligatorio)',rule.engine,{choices:[{value:'',label:'Selecciona un motor de voz'},...this.data.engines],required:true});
        if (!this.data.engines.length) root.append(node('p','Configura antes una integración de texto a voz en Home Assistant.',{class:'warning'}));
        this.field(root,'before','Texto antes del valor',rule.before,{maxlength:1000});
        this.field(root,'after','Texto después del valor',rule.after,{maxlength:1000});
        this.field(root,'unit','Añadir la unidad del sensor',rule.unit,{type:'checkbox'});
        const trigger = this.field(root,'trigger','Cuándo hablar',rule.trigger,{choices:Object.entries(triggers).map(([value,label]) => ({value,label}))});
        const threshold = this.field(root,'threshold','Umbral numérico',rule.threshold,{type:'number',step:'any'});
        const updateThreshold = () => {const needed = ['above','below'].includes(trigger.value); threshold.required = needed; threshold.parentElement.hidden = !needed;};
        trigger.addEventListener('change',updateThreshold); updateThreshold();
        this.field(root,'cooldown','Intervalo mínimo entre avisos (segundos)',rule.cooldown,{type:'number',min:0,max:86400,step:1,required:true});
      }
      this.field(root,'priority','Prioridad del aviso',rule.priority,{choices:Object.entries(labels).map(([value,label]) => ({value,label}))});
      this.$('save').disabled = false;
    } catch (err) {this.$('form-error').textContent = this.error(err);}
  }
  async save() {
    if (this.saving || this.$('save').disabled) return;
    const rule = {...this.editing.rule};
    for (const [key,input] of Object.entries(this.controls)) {
      if (['sound','close_sound'].includes(key)) {if (input.value) rule[key] = {media_content_id:input.value,media_content_type:'music'}; else delete rule[key];}
      else if (input.type === 'checkbox') rule[key] = input.checked;
      else if (input.type === 'number') {if (input.value === '') delete rule[key]; else rule[key] = Number(input.value);}
      else rule[key] = input.value;
    }
    this.saving = true; this.$('save').disabled = true; this.$('cancel').disabled = true;
    const guard = e => e.preventDefault(); this.dialog.addEventListener('cancel',guard);
    try {
      this.data = await this.request({action:'save',kind:this.editing.kind,key:this.editing.key,revision:this.editRevision,rule});
      this.dialog.close(); this.renderList(); this.$('results').focus(); this.$('message').textContent = 'Cambios guardados.';
    } catch (err) {this.$('form-error').textContent = this.error(err); this.$('form-error').focus();}
    finally {this.saving = false;this.$('save').disabled = false;this.$('cancel').disabled = false;this.dialog.removeEventListener('cancel',guard);}
  }
}
if (!customElements.get('jacksignal-panel')) customElements.define('jacksignal-panel',JackSignalPanel);
