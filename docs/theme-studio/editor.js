'use strict';
const $ = id => document.getElementById(id);
// Keep these defaults aligned with lib/spotlight_config.py.
const defaults = {background:'#161b22',foreground:'#d5dce4',selection:'#283747',selected_foreground:'#ffffff',accent:'#7dd3a8',muted:'#8093a8',border:'#485463',hint:'245',command:'114',tab_foreground:'#161b22',error:'#ff7b72'};
const categories = {WINDOWS:'81',PANES:'114',SESSIONS:'221',NAVIGATION:'177',CLIPBOARD:'216',CONFIGURATION:'110',PERSISTENCE:'150',ACTIONS:'81',SYSTEM:'81',DOCKER:'114'};
const descriptions = {background:'Main view & popup',foreground:'Result & preview text',selection:'Selected row background',selected_foreground:'Selected row text',accent:'Prompt, match, tab & frame',muted:'Inactive tabs & result count',border:'Preview divider',hint:'Shortcuts & setting values',command:'Action preview command',tab_foreground:'Active tab text',error:'Installation error message'};
const ansiDefault = ['#000000','#cd0000','#00cd00','#cdcd00','#0000ee','#cd00cd','#00cdcd','#e5e5e5','#7f7f7f','#ff0000','#00ff00','#ffff00','#5c5cff','#ff00ff','#00ffff','#ffffff'];
const presets = {
 'brand-dark':{colors:{background:'#17130c',foreground:'#f8f0dc',selection:'#302718',selected_foreground:'#fff9ee',accent:'#ffc94a',muted:'#b9aa86',border:'#574831',hint:'#d9bf83',command:'#ffe19a',tab_foreground:'#231a05',error:'#ff8b79'},categories:{WINDOWS:'#ffc94a',PANES:'#89d2c5',SESSIONS:'#ffad86',NAVIGATION:'#d6b5eb',CLIPBOARD:'#e6bf89',CONFIGURATION:'#aabff1',PERSISTENCE:'#b8d995',ACTIONS:'#ffc94a',SYSTEM:'#ffc94a',DOCKER:'#89d2c5'}},
 'brand-light':{colors:{background:'#fbf5e9',foreground:'#2b2112',selection:'#f1e5ca',selected_foreground:'#2b2112',accent:'#8a4b00',muted:'#6a5a3c',border:'#c8b99c',hint:'#745a38',command:'#744000',tab_foreground:'#fff9ee',error:'#ad3f30'},categories:{WINDOWS:'#8a4b00',PANES:'#176e65',SESSIONS:'#aa502f',NAVIGATION:'#76508b',CLIPBOARD:'#945a25',CONFIGURATION:'#365a91',PERSISTENCE:'#526d2b',ACTIONS:'#8a4b00',SYSTEM:'#8a4b00',DOCKER:'#176e65'}},
 monokai:{colors:themePalettes.monokai.colors,categories:themePalettes.monokai.categories},
 default:{colors:defaults,categories},
 terminal:{colors:{background:'default',foreground:'7',selection:'8',selected_foreground:'15',accent:'2',muted:'8',border:'4',hint:'8',command:'6',tab_foreground:'0',error:'1'},categories:{WINDOWS:'6',PANES:'2',SESSIONS:'3',NAVIGATION:'5',CLIPBOARD:'3',CONFIGURATION:'4',PERSISTENCE:'2',ACTIONS:'6',SYSTEM:'6',DOCKER:'2'}},
 dusk:{colors:{background:'#211e30',foreground:'#dfd9ef',selection:'#3b3351',selected_foreground:'#ffffff',accent:'#c4a7e7',muted:'#978ba9',border:'#635577',hint:'#a6a0ba',command:'#9ed9ce',tab_foreground:'#211e30',error:'#f49aaa'},categories:{WINDOWS:'#a4c8ef',PANES:'#9ed9ce',SESSIONS:'#ead8a6',NAVIGATION:'#c4a7e7',CLIPBOARD:'#edba9e',CONFIGURATION:'#9eb8eb',PERSISTENCE:'#c4d49b',ACTIONS:'#a4c8ef',SYSTEM:'#a4c8ef',DOCKER:'#9ed9ce'}},
 paper:{colors:{background:'#f5f2e8',foreground:'#393e39',selection:'#dce5d7',selected_foreground:'#172b20',accent:'#397055',muted:'#737a6e',border:'#b9beb0',hint:'#7d7465',command:'#326a7c',tab_foreground:'#ffffff',error:'#b73c40'},categories:{WINDOWS:'#286b8d',PANES:'#38734a',SESSIONS:'#8b6918',NAVIGATION:'#8356a0',CLIPBOARD:'#a36232',CONFIGURATION:'#4967a0',PERSISTENCE:'#687c31',ACTIONS:'#286b8d',SYSTEM:'#286b8d',DOCKER:'#38734a'}}
};
// Static fixtures only: selecting a row never invokes a shell.
const row = (title,category,hint,command,description='') => ({title,category,hint,command,description});
const commandRows = [
 row('New window','WINDOWS','prefix c','tmux new-window','Create a new window in the current session.'),
 row('Split pane horizontally','PANES','prefix %','tmux split-window -h','Split the active pane into two columns.'),
 row('New session','SESSIONS','prefix :','tmux new-session -s work','Start a fresh workspace.'),
 row('Next window','NAVIGATION','prefix n','tmux next-window','Move to the next window.'),
 row('Copy mode','CLIPBOARD','prefix [','tmux copy-mode','Browse and copy terminal output.'),
 row('Reload configuration','CONFIGURATION','prefix r','tmux source-file ~/.tmux.conf','Reload tmux configuration.'),
 row('Save environment','PERSISTENCE','prefix C-s','tmux run-shell ~/.tmux/plugins/tmux-resurrect/scripts/save.sh','Save windows and pane layouts.'),
 row('Install action file…','ACTIONS','HTTPS URL','','Download an HTTPS TOML or Navi .cheat file to your user configuration. GitHub file links are accepted.'),
 row('Update system','SYSTEM','packages','sudo apt update && sudo apt upgrade','Refresh package lists and upgrade installed packages.'),
 row('List containers','DOCKER','docker ps','docker ps -a','List running and stopped containers.'),
 row('Compose logs','Docker Compose','logs','docker compose logs --tail 100 -f','Follow recent application logs. Docker-prefixed categories share the DOCKER color.'),
 row('Restart container','DOCKER','restart','docker restart <container>','Choose a container to restart.'),
 row('Git status','Git','status','git status --short','An unmapped category falls back to accent. Add a custom category color below to override it.')
];
const scenes = {
 commands:commandRows,
 parameters:[row('api-dev','', 'e483f21','docker restart api-dev','Development API'),row('postgres','', 'b932a0d','docker restart postgres','Local PostgreSQL database'),row('redis','', '07c2f41','docker restart redis','Local cache')],
 errors:[row('Back to Commands','','','','Return to the command palette.'),row('Edit URL','','','','Correct the action file URL and try again.')],
 settings:[row('Theme','Core','my-theme','','Choose a built-in or user theme. Applies immediately; the popup frame updates on next open.'),row('Recent command count','Core','5','','Most recent invocations appear first when search is empty. Choose 0 to disable history; maximum 100.'),row('Clear recent commands','Core','Clear…','','Remove saved invocations. Command definitions are preserved.'),row('Default session','tmux','work','','Module setting contributed by tmux.')]
};
let theme = structuredClone(presets['brand-dark']), ansi = [...ansiDefault], scene='commands', selected=9, visible=[], terminalBg='#12161c', terminalFg='#d5dce4';
const storageKey='spotlight-theme-studio-v1';
function validColor(value){return /^(#[0-9a-f]{6}|default|[0-9]+)$/i.test(value) && (value.startsWith('#') || value === 'default' || /^\d+$/.test(value) && Number(value)<=255);}
function validateTheme(candidate){
 if(!candidate || !candidate.colors || !candidate.categories) throw Error('Expected colors and categories tables.');
 for(const [key,value] of Object.entries(candidate.colors)) if(!Object.hasOwn(defaults,key) || typeof value!=='string' || !validColor(value)) throw Error(`Invalid color: ${key}`);
 for(const [key,value] of Object.entries(candidate.categories)) if(!key || /[\x00-\x1f]/.test(key) || typeof value!=='string' || !validColor(value)) throw Error(`Invalid category: ${key}`);
 return {colors:{...defaults,...candidate.colors},categories:{...categories,...Object.fromEntries(Object.entries(candidate.categories).map(([k,v])=>[k.toUpperCase(),v]))}};
}
function color(value,background=false){
 if(value==='default') return background ? terminalBg : terminalFg;
 if(value.startsWith('#')) return value;
 const n=Number(value);
 if(n<16) return ansi[n];
 if(n>=232){const v=(8+10*(n-232)).toString(16).padStart(2,'0');return `#${v}${v}${v}`;}
 const levels=[0,95,135,175,215,255], v=n-16;
 return '#'+[Math.floor(v/36),Math.floor(v/6)%6,v%6].map(i=>levels[i].toString(16).padStart(2,'0')).join('');
}
function status(message){$('status').textContent=message;}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify({theme,name:$('theme-name').value,ansi,terminalBg,terminalFg,preset:$('preset').value}));}catch{status('Browser storage unavailable. Download to keep your theme.');}}
function toml(){return '# Spotlight theme — created with Theme Studio\n[colors]\n'+Object.entries(theme.colors).map(([k,v])=>`${k} = ${JSON.stringify(v)}`).join('\n')+'\n\n[categories]\n'+Object.entries(theme.categories).map(([k,v])=>`${JSON.stringify(k)} = ${JSON.stringify(v)}`).join('\n')+'\n';}
function apply(){
 for(const [key,value] of Object.entries(theme.colors)) $('terminal').style.setProperty('--'+key,color(value,key==='background'||key==='selection'));
 $('terminal').style.setProperty('--tab_background',color(theme.colors.accent,true));
 document.documentElement.style.setProperty('--terminal-bg',terminalBg);
 $('toml').textContent=toml();
 $('coverage').textContent=`11 roles · ${Object.keys(theme.categories).length} categories`;
 renderPreview();renderSwatches();persist();
}
function buildControls(){
 const root=$('color-controls');root.replaceChildren();
 for(const [group,values] of Object.entries(theme)){
  const heading=document.createElement('h3');heading.className='group-title';heading.textContent=group==='colors'?'INTERFACE COLORS':'CATEGORY COLORS';root.append(heading);
  for(const [key,value] of Object.entries(values)){
   const wrap=document.createElement('div');wrap.className='color-row';
   const picker=document.createElement('input');picker.type='color';picker.className='swatch';picker.value=color(value,key==='background'||key==='selection');picker.setAttribute('aria-label',`${key} color picker`);
   const pickerControl=document.createElement('label');pickerControl.className='color-picker';pickerControl.append(picker,'Choose color');
   const label=document.createElement('label');label.className='color-label';label.htmlFor=`${group}-${key}`;label.append(group==='colors'?key.replaceAll('_',' '):key.toLowerCase());
   const small=document.createElement('small');small.textContent=descriptions[key]||'Category label';label.append(small);
   const input=document.createElement('input');input.className='value-input';input.id=label.htmlFor;input.value=value;input.spellcheck=false;input.setAttribute('aria-label',`${key} color value`);input.title='Use #RRGGBB, a palette index 0–255, or default';
   input.addEventListener('input',()=>{const v=input.value.trim();const valid=validColor(v);input.setAttribute('aria-invalid',String(!valid));if(valid){theme[group][key]=v;picker.value=color(v,key==='background'||key==='selection');apply();}else status('Use #RRGGBB, a palette index 0–255, or default.');});
   picker.addEventListener('input',()=>{theme[group][key]=picker.value;input.value=picker.value;input.setAttribute('aria-invalid','false');apply();});
   wrap.append(label,pickerControl,input);root.append(wrap);
  }
 }
 buildSwatchTargets();
 const add=document.createElement('button');add.textContent='+ Add category';add.addEventListener('click',()=>{const key=prompt('Category name (for example Git):');if(key===null) return;const name=key.trim().toUpperCase();if(!name || /[\x00-\x1f]/.test(name)){status('Enter a category name without control characters.');return;}theme.categories[name]=theme.categories[name]||theme.colors.accent;buildControls();apply();status(`Added ${name}. Import a theme to load additional category colors too.`);});root.append(add);
}
function buildSwatchTargets(){
 const select=$('swatch-target'), previous=select.value;
 select.replaceChildren();
 for(const [group,values] of Object.entries(theme)){
  const options=document.createElement('optgroup');options.label=group==='colors'?'Interface':'Categories';
  for(const key of Object.keys(values)){
   const option=document.createElement('option');option.value=JSON.stringify([group,key]);option.textContent=key.replaceAll('_',' ');options.append(option);
  }
  select.append(options);
 }
 select.value=[...select.options].some(option=>option.value===previous)?previous:JSON.stringify(['colors','accent']);
}
function renderSwatches(){
 const target=$('swatch-target').value;if(!target)return;
 const [group,key]=JSON.parse(target), used=new Set(Object.values(theme).flatMap(values=>Object.entries(values).map(([k,v])=>color(v,k==='background'||k==='selection').toLowerCase())));
 const library=$('swatch-source').value;
 const swatches=library==='current'?[...new Map(Object.entries(theme).flatMap(([group,values])=>Object.entries(values).map(([key,value])=>{const rgb=color(value,key==='background'||key==='selection').toLowerCase();return [rgb,{value:rgb,name:key.replaceAll('_',' '),sources:[]}];}))).values()]:themePalettes[library].swatches;
 const unused=swatches.filter(swatch=>!used.has(swatch.value)).length;
 $('swatch-info').textContent=`${swatches.length} colors · ${unused} unused in your theme`;
 const container=$('ready-swatches');container.replaceChildren();
 for(const swatch of swatches){
  const inUse=used.has(swatch.value);if($('unused-only').checked&&inUse)continue;
  const button=document.createElement('button');button.type='button';button.className='palette-swatch';button.dataset.value=swatch.value;
  button.title=swatch.name+' · '+swatch.value+'\n'+swatch.sources.map(source=>source.role+': '+source.value).join('\n');
  button.setAttribute('aria-label',`Apply ${swatch.name} (${swatch.value}) to ${key}`);button.setAttribute('aria-pressed',String(color(theme[group][key],key==='background'||key==='selection').toLowerCase()===swatch.value));
  const chip=document.createElement('span');chip.className='palette-chip';chip.style.backgroundColor=swatch.value;chip.setAttribute('aria-hidden','true');
  const name=document.createElement('span');name.className='swatch-name';name.textContent=swatch.name;
  const availability=document.createElement('small');availability.textContent=inUse?'In use':'Unused';
  button.append(chip,name,availability);
  button.addEventListener('click',()=>{theme[group][key]=swatch.value;buildControls();apply();status(`Applied ${swatch.name} to ${key}.`);[...container.children].find(element=>element.dataset.value===swatch.value)?.focus({preventScroll:true});});
  container.append(button);
 }
 if(!container.children.length){const empty=document.createElement('p');empty.textContent='No unused colors in this library. Choose Monokai or show all colors.';container.append(empty);}
}
for(const id of ['swatch-source','swatch-target','unused-only']) $(id).addEventListener('change',renderSwatches);
function highlighted(text){
 const fragment=document.createDocumentFragment(), query=$('search').value.toLowerCase(), index=query?text.toLowerCase().indexOf(query):-1;
 if(index<0){fragment.append(text);return fragment;}
 fragment.append(text.slice(0,index));const match=document.createElement('mark');match.textContent=text.slice(index,index+query.length);fragment.append(match,text.slice(index+query.length));return fragment;
}
function categoryColor(category){let key=category.toUpperCase();if(key.startsWith('DOCKER'))key='DOCKER';return color(theme.categories[key]||theme.colors.accent);}
function span(text,className){const el=document.createElement('span');el.className=className||'';el.textContent=text;return el;}
function renderPreview(){
 const tabs=$('terminal-tabs');tabs.replaceChildren();
 if(scene==='parameters'){tabs.append(span(' Restart container ','active'),span('› container',''));tabs.lastChild.className='crumb';}
 else if(scene==='errors') tabs.append(span(' Commands › Install action file ','active'));
 else for(const name of ['Commands','Files','Sessions','Windows','Panes','Settings']) tabs.append(span(name,(scene==='settings'?name==='Settings':name==='Commands')?'active':''));
 const samples=scene==='commands' ? [...commandRows,...Object.keys(theme.categories).filter(key=>!commandRows.some(r=>r.category.toUpperCase()===key)).map(key=>row('Custom category sample',key,'sample','echo preview','Preview for your custom category color.'))] : scenes[scene];
 const query=$('search').value.toLowerCase();visible=samples.filter(r=>(r.title+' '+r.category+' '+r.hint).toLowerCase().includes(query));
 selected=Math.min(Math.max(selected,0),visible.length-1);
 $('result-count').textContent=`${visible.length}/${samples.length}`;
 const results=$('results');results.replaceChildren();
 if(!visible.length){const empty=span('  No matching results','hint');results.append(empty);}
 visible.forEach((r,index)=>{
  const button=document.createElement('button');button.type='button';button.className='result'+(index===selected?' selected':'');button.setAttribute('role','option');button.setAttribute('aria-selected',String(index===selected));
  button.append(span(index===selected?'▸':'','pointer'));
  const title=span('');title.append(highlighted(r.title));button.append(title);
  const category=span('','category');category.append(highlighted(r.category));category.style.setProperty('--category-color',categoryColor(r.category));button.append(category);
  const hint=span('','hint');hint.append(highlighted(scene==='settings'&&r.title==='Theme'?$('theme-name').value:r.hint));button.append(hint);
  button.addEventListener('click',()=>{selected=index;renderPreview();});results.append(button);
 });
 const detail=$('detail');detail.replaceChildren();const r=visible[selected];
 if(scene==='errors'){
  detail.append(span('Could not install action file','error'),'\n\n',span('HTTP 404: Not Found\n\nhttps://example.com/actions.toml','error'),'\n\nCheck the URL and try again.\n\nChoose “Edit URL” to retry.');
 }else if(r){
  if(scene==='parameters') detail.append('Restart container\n\nChoose a container to restart.\n\n',span('docker restart <container>',''),'\n\n',r.description);
  else detail.append(r.category.toUpperCase(),'\n\n',r.description,'\n\n',span(r.command,'command'),r.command?'\n\n':'',scene==='commands'&&r.command?'built-in sample action':'');
 }
}
function exportable(){
 if(!/^[a-z][a-z0-9_-]*$/.test($('theme-name').value)){status('Theme name must start with a lowercase letter and use lowercase letters, digits, _ or -.');$('theme-name').focus();return false;}
 if(document.querySelector('[aria-invalid="true"]')){status('Fix the invalid color before exporting.');return false;}return true;
}
// A deliberately small TOML reader for Spotlight's flat, string-only theme tables.
// Unsupported TOML constructs fail explicitly rather than being silently dropped.
function parseToml(source){
 const data={colors:{},categories:{}},tables=new Set();let table='';
 for(const [index,line] of source.replace(/^\uFEFF/,'').split(/\r?\n/).entries()){
  const trimmed=line.trim();if(!trimmed||trimmed.startsWith('#'))continue;
  const header=trimmed.match(/^\[(colors|categories)\]\s*(?:#.*)?$/);
  if(header){table=header[1];if(tables.has(table)) throw Error(`Line ${index+1}: repeated table.`);tables.add(table);continue;}
  const entry=trimmed.match(/^("(?:[^"\\]|\\.)*"|'[^']*'|[\w-]+)\s*=\s*("(?:[^"\\]|\\.)*"|'[^']*')\s*(?:#.*)?$/);
  if(!table||!entry)throw Error(`Line ${index+1}: expected [colors], [categories], or key = "color". Use flat tables and single-line quoted strings.`);
  const decode=text=>text.startsWith('"')?JSON.parse(text):text.startsWith("'")?text.slice(1,-1):text;
  const key=decode(entry[1]),value=decode(entry[2]);
  if(Object.hasOwn(data[table],key))throw Error(`Line ${index+1}: duplicate key ${key}.`);
  Object.defineProperty(data[table],key,{value,enumerable:true,configurable:true,writable:true});
 }
 return validateTheme(data);
}
$('search').addEventListener('input',()=>{selected=0;renderPreview();});
$('results').addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();selected=Math.max(0,Math.min(visible.length-1,selected+(event.key==='ArrowDown'?1:-1)));renderPreview();$('results').querySelector('[aria-selected=true]')?.scrollIntoView({block:'nearest'});}});
for(const button of document.querySelectorAll('[data-scene]')) button.addEventListener('click',()=>{scene=button.dataset.scene;selected=0;$('search').value='';for(const b of document.querySelectorAll('[data-scene]'))b.setAttribute('aria-pressed',String(b===button));renderPreview();});
$('preset').addEventListener('change',()=>{theme=structuredClone(presets[$('preset').value]);buildControls();apply();status('Preset applied.');});
$('reset').addEventListener('click',()=>{theme=structuredClone(presets[$('preset').value]);buildControls();apply();status('Palette reset to the selected preset.');});
$('theme-name').addEventListener('input',()=>{persist();renderPreview();});
$('download').addEventListener('click',()=>{if(!exportable())return;const url=URL.createObjectURL(new Blob([toml()],{type:'text/plain'}));const link=document.createElement('a');link.href=url;link.download=$('theme-name').value+'.toml';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Theme downloaded. Select it in Spotlight → Settings → Theme.');});
$('copy').addEventListener('click',async()=>{if(!exportable())return;try{await navigator.clipboard.writeText(toml());status('TOML copied.');}catch{const selection=getSelection(),range=document.createRange();$('toml').parentElement.open=true;range.selectNodeContents($('toml'));selection.removeAllRanges();selection.addRange(range);status('Clipboard unavailable. TOML selected — press Ctrl/Cmd+C.');}});
$('import').addEventListener('click',()=>$('file').click());
$('file').addEventListener('change',async()=>{const file=$('file').files[0];if(!file)return;try{if(file.size>100000)throw Error('Theme file is too large (100 KB maximum).');const next=parseToml(await file.text());theme=next;const name=file.name.replace(/\.toml$/i,'');if(/^[a-z][a-z0-9_-]*$/.test(name))$('theme-name').value=name;buildControls();apply();status(`Imported ${file.name}. Missing entries use Spotlight defaults.`);}catch(error){status(`Import failed: ${error.message}`);}finally{$('file').value='';}});
function buildAnsiControls(){
 $('ansi-controls').replaceChildren();ansi.forEach((value,index)=>{const label=document.createElement('label');label.append(String(index));const input=document.createElement('input');input.type='color';input.value=value;input.setAttribute('aria-label',`ANSI slot ${index}`);input.addEventListener('input',()=>{ansi[index]=input.value;buildControls();apply();});label.append(input);$('ansi-controls').append(label);});
}
for(const [id,key] of [['terminal-bg','bg'],['terminal-fg','fg']]) $(id).addEventListener('input',()=>{if(key==='bg')terminalBg=$(id).value;else terminalFg=$(id).value;buildControls();apply();});
try{const saved=JSON.parse(localStorage.getItem(storageKey));if(saved){theme=validateTheme(saved.theme);if(Object.hasOwn(presets,saved.preset))$('preset').value=saved.preset;if(/^[a-z][a-z0-9_-]*$/.test(saved.name))$('theme-name').value=saved.name;if(Array.isArray(saved.ansi)&&saved.ansi.length===16&&saved.ansi.every(c=>/^#[0-9a-f]{6}$/i.test(c)))ansi=saved.ansi;if(/^#[0-9a-f]{6}$/i.test(saved.terminalBg))terminalBg=saved.terminalBg;if(/^#[0-9a-f]{6}$/i.test(saved.terminalFg))terminalFg=saved.terminalFg;}}catch{status('Started with the default palette.');}
$('terminal-bg').value=terminalBg;$('terminal-fg').value=terminalFg;
buildControls();buildAnsiControls();apply();
