import ast
import io
import mimetypes
import subprocess
from pathlib import Path
from urllib import parse
from html.parser import HTMLParser
import pytest

ROOT = Path(__file__).resolve().parents[1]


def node(script):
    result = subprocess.run(['node', '-'], input=script, text=True, encoding='utf-8', cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_auto_and_custom_intent_cross_actual_frontend_bridge():
    node(r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
global.window={};
require('./src/core/namespace.js');
require('./agent-runtime.js');
const source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('function getEffectiveMaxTokens(');
const end=source.indexOf('function updateOutputBudgetSummary(',start);
const context={els:{maxTokens:{value:'auto'}},t:k=>k};
vm.runInNewContext(source.slice(start,end),context);
for(const model of ['deepseek-flash','unknown','claude-sonnet-4-5','gpt-5.4']) assert.equal(context.getEffectiveMaxTokens(model),0);
const sent=[];
global.fetch=async(url, options)=>{sent.push(JSON.parse(options.body)); return {ok:true,json:async()=>({agentRunId:'fixture'})};};
(async()=>{
 for(const [value,want] of [['auto',0],['',0],['   ',0],['4096',4096],['12345',12345]]) {
  context.els.maxTokens.value=value;
  const tokens=context.getEffectiveMaxTokens('unknown'); assert.equal(tokens,want);
  await window.Code.agent.runtime.createAgentRun({sessionId:'fixture',payload:{model:'unknown',max_tokens:tokens},keys:[]});
  assert.deepEqual(sent.at(-1).outputPreference,want?{version:1,mode:'manual',tokens:want}:{version:1,mode:'auto'});
 }
 for(const value of ['0','-1','1.5','Infinity','1e5','2000001']) {
  context.els.maxTokens.value=value; assert.throws(()=>context.getEffectiveMaxTokens('unknown'));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
''')


def test_auto_zero_never_reaches_an_old_server_from_the_new_ui():
    node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8'), start=source.indexOf('function assertAutoOutputSupported(');
const end=source.indexOf('\n}',start)+2;
const context={state:{},t:k=>k};vm.createContext(context);vm.runInContext(source.slice(start,end),context);
for(const protocol of [undefined,'','future']) {
 context.state.outputBudgetProtocol=protocol;
 assert.throws(()=>context.assertAutoOutputSupported({max_tokens:0}),e=>e.errorCode==='output_budget_client_upgrade_required');
}
context.state.outputBudgetProtocol='coding-output-v1';context.assertAutoOutputSupported({max_tokens:0});
''')


def test_real_i18n_identity_and_notification_survive_repaints_both_languages():
    node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8');
const identity=source.slice(source.indexOf('let _baseDocumentTitle = document.title;'),source.indexOf('function setAgentProjectionShadowEnabled('));
const clear=source.slice(source.indexOf('function clearPermissionNotify()'),source.indexOf('document.addEventListener("visibilitychange"'));
for(const mode of ['dev','release']) {
 const title=mode==='dev'?'Code Dev':'Code';
 const product={textContent:'Code'};
 const document={title,documentElement:{dataset:{instanceMode:mode}},querySelectorAll:()=>[],querySelector:()=>null,
  getElementById:id=>id==='productName'?product:null};
 const context={window:{document},document,els:{productName:product},state:{},clearInterval:()=>{}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('src/core/namespace.js','utf8'),context);
 vm.runInContext(fs.readFileSync('src/core/i18n.js','utf8'),context);
 vm.runInContext(identity+clear,context);
 assert.equal(product.textContent,title);
 let language='zh';
 const i18n=context.window.Code.core.i18n.createI18nRuntime({getDocument:()=>document,getLanguage:()=>language});
 for(language of ['zh','en']) {
  i18n.applyI18n(); i18n.applyI18n(); // initialization plus welcome repaint uses the same real function
  assert.equal(document.title,title); assert.equal(product.textContent,title);
  vm.runInContext('_pendingPermNotify=true;document.title="[pending] fixture";',context);
  i18n.applyI18n(); context.applyInstanceIdentity(mode);
  assert.equal(document.title,'[pending] fixture');
  context.clearPermissionNotify(); assert.equal(document.title,title);
  assert.equal(i18n.t('maxTokens'),language==='en'?'Output per request':'单次输出');
  assert.ok(!i18n.t('errLabelOutputTruncatedTools').startsWith('errLabel'));
 }
}
''')


def test_default_output_ui_hides_values_inside_closed_advanced_details():
    class Parser(HTMLParser):
        def __init__(self): super().__init__(); self.advanced=False; self.seen=False
        def handle_starttag(self, tag, attrs):
            a=dict(attrs)
            if tag=='details' and a.get('class')=='output-budget-advanced':
                assert 'open' not in a; self.advanced=True
            if a.get('id')=='maxTokens':
                assert self.advanced and tag=='input' and a.get('value')==''; self.seen=True
            if a.get('id')=='outputBudgetSummary':
                assert self.advanced and a.get('data-i18n')=='auto'
        def handle_endtag(self,tag):
            if tag=='details': self.advanced=False
    parser=Parser(); parser.feed((ROOT/'index.html').read_text(encoding='utf-8')); assert parser.seen


def test_truncated_projection_is_display_only_for_the_next_request():
    node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.window={}; require('./src/core/namespace.js'); require('./src/agent/model-request.js');
const source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('function projectAgentModelCompleted('), end=source.indexOf('function findAgentCompactionProjection(',start);
const assistant={role:'assistant',content:'partial visible body',streaming:true,meta:{toolCalls:[{id:'partial'}]}};
const ctx={messages:[assistant],run:{},sessionId:'s'};
const context={findAgentAssistantByRuntime:()=>assistant,markModelResponseStarted:()=>{},
 isInternalGoalToolName:()=>false,agentEventMeta:()=>({}),setSessionLastUsage:()=>{},updateUsage:()=>{},
 toolProgressSummary:()=>'',getSelectedModel:()=>'',Date};
vm.createContext(context); vm.runInContext(source.slice(start,end),context);
context.projectAgentModelCompleted(ctx,{data:{runtimeRunId:'r',outcome:'output_truncated',toolCalls:[],usage:{},outputDiagnostic:{version:1}}});
assert.equal(assistant.meta.skipApi,true); assert.equal(assistant.meta.toolCalls.length,0);
assert.equal(window.Code.agent.modelRequest.mapMessageForApi(assistant),null);
''')


def test_actual_settings_template_events_storage_and_restore_both_languages():
    node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('app.js','utf8'), settings=fs.readFileSync('src/features/settings.js','utf8');
const between=(source,a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
for(const language of ['zh','en']) for(const stored of ['auto','4096','12345']) {
 class Element {
  constructor(value=''){this.value=value;this.dataset={};this.listeners={};this.textContent='';}
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
  dispatchEvent(event){event.currentTarget=this;for(const fn of this.listeners[event.type]||[])fn(event);}
  setCustomValidity(value){this.validation=value;}
  reportValidity(){this.reported=true;}
  querySelectorAll(){return [];}
 }
 const nodes=new Map(); const byId=id=>nodes.get(id)||null;
 nodes.set('outputBudgetSummary',new Element());
 const store=new Map([['code-max-tokens',stored],['code-response-style-v2','unchanged-style'],['code-context-budget','400000']]);
 const storage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
 const els={apiKey:new Element(),baseUrl:new Element(),maxTokens:new Element(),contextBudget:new Element('400000'),
  temperature:new Element('0.2'),toolPreset:new Element('default'),modelListBox:{innerHTML:''}};
 const context={window:{},els,document:{getElementById:byId},localStorage:storage,storage,byId,
  WORKBAR_URL:'https://fixture.invalid',state:{},getSelectedModel:()=>'',normalizeContextBudgetSetting:()=>{},
  reasoningPreference:{mode:'v2'},getPermissionProfile:()=>'read',updateModePromptPreview:()=>{},
  updateReasoningPicker:()=>{},loadKeyConfig:()=>[],serializeKeys:()=>'',renderedModelCount:()=>0,
  escapeHtml:s=>String(s),renderKeyEditor:()=>'',getPlatformAuth:()=>null,showToast:()=>{},
  syncKeysFromPlatform:()=>{},refreshSettingsModelList:()=>{},updateContextBudgetStatus:()=>{},bindKeyEditorEvents:()=>{}};
 context.global=context.window; context.window.Event=class{constructor(type){this.type=type;}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('src/core/namespace.js','utf8'),context);
 vm.runInContext(fs.readFileSync('src/core/i18n.js','utf8'),context);
 vm.runInContext(fs.readFileSync('src/agent/compaction.js','utf8'),context);
 Object.assign(context,context.window.Code.agent.compaction);
 vm.runInContext(between(app,'function parseContextBudgetInput(','function saveLocalSettings('),context);
 context.updateContextBudgetStatus=()=>context.normalizeContextBudgetSetting();
 context.t=k=>context.window.Code.core.i18n.translate(k,{},language);
 context.window.Code.agent.systemPrompt={RESPONSE_DETAILS:['standard'],RESPONSE_TONES:['neutral'],
  readResponseStylePreference:()=>({snapshot:{detail:'standard',tone:'neutral'}})};
 vm.runInContext(between(app,'function getEffectiveMaxTokens(','// Unified picker events are installed below.'),context);
 // Only the actual output helpers, settings save function, and bound output event are required here.
 vm.runInContext(between(app,'function saveLocalSettings(','function handleUiSlashCommand('),context);
 vm.runInContext(between(app,'els.maxTokens.addEventListener("change"','els.contextBudget.addEventListener("change"'),context);
 vm.runInContext(between(app,'  const savedMax = localStorage.getItem("code-max-tokens")','  const savedContextBudget ='),context);
 const container={set innerHTML(html){this.html=html;
  for(const match of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"[^>]*>/g)) {
   const node=new Element(match[0].match(/\bvalue="([^"]*)"/)?.[1]||'');node.tagName=match[1].toUpperCase();
   node.dataset.i18n=match[0].match(/data-i18n="([^"]*)"/)?.[1];nodes.set(match[2],node);
  }
 }};
 vm.runInContext(between(settings,'    function renderModelsPanel(container)','    function renderSystemPanel('),context);
 context.renderModelsPanel(container);
 let control=byId('settingsMaxTokens'); assert.equal(control.tagName,'INPUT');assert.equal(control.value,stored==='auto'?'':stored);
 assert.ok(!container.html.includes('<select id="settingsMaxTokens">'));
 assert.ok(container.html.includes('<details class="output-budget-advanced">'));
 assert.ok(container.html.includes('aria-labelledby="settingsOutputBudgetLabel settingsOutputBudgetSummary"'));
 assert.ok(!container.html.includes('data-i18n="outputBudgetAdvanced"'));
 assert.ok(container.html.indexOf('<details class="response-style-advanced">')<container.html.indexOf('id="settingsContextBudget"'));
 assert.ok(container.html.includes('data-i18n="contextLimitSetting"'));
 assert.equal(store.get('code-context-budget'),'400000');
 assert.equal(context.getModelContextResolution('unknown',16384).contextBudgetTokens,400000);
 assert.ok(container.html.indexOf('class="output-budget-advanced"')<container.html.indexOf('id="settingsMaxTokens"'));
 assert.ok(!container.html.includes('<option value="auto">'));
 for(const value of ['54321','','   ','auto','65536']) {
  control.value=value;control.dispatchEvent({type:'change'});
  const auto=!value.trim()||value==='auto',display=auto?'':value;
  assert.equal(els.maxTokens.value,display);assert.equal(store.get('code-max-tokens'),auto?'auto':value);
  assert.equal(byId('settingsOutputBudgetSummary').textContent,context.t(auto?'auto':'outputBudgetManual'));
  context.renderModelsPanel(container);control=byId('settingsMaxTokens');assert.equal(control.value,display);
 }
 control.value='1.5';control.dispatchEvent({type:'change'});
 assert.equal(store.get('code-max-tokens'),'65536');assert.equal(els.maxTokens.value,'65536');assert.ok(control.reported);
 assert.equal(store.get('code-response-style-v2'),'unchanged-style');
 for(const [value,want] of [['128K',128000],['',null],['400000',400000]]) {
  const contextControl=byId('settingsContextBudget');contextControl.value=value;contextControl.dispatchEvent({type:'change'});
  assert.equal(store.get('code-context-budget'),want===null?'auto':String(want));
  context.renderModelsPanel(container);
  assert.equal(byId('settingsContextBudget').value,els.contextBudget.value);
  assert.equal(context.getModelContextResolution('unknown',65536).contextBudgetTokens,want);
 }
 byId('settingsContextBudget').value='12g';byId('settingsContextBudget').dispatchEvent({type:'change'});
 assert.equal(store.get('code-context-budget'),'400000');assert.equal(context.getContextBudgetTokens(),400000);
}
''')


@pytest.mark.parametrize('mode,title',[('dev','Code Dev'),('release','Code')])
def test_initial_html_and_classic_identity_use_instance_mode(tmp_path, mode, title):
    tree=ast.parse((ROOT/'server.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CodeHandler')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='do_GET')
    html=(ROOT/'index.html').read_bytes()
    for rel in ['index.html','dist/frontend/index.html','dist/frontend/index.classic.html']:
        path=tmp_path/rel; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(html)
    scope={'APP_DIR':tmp_path,'INSTANCE_MODE':mode,'parse':parse,'mimetypes':mimetypes}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'server.py:do_GET','exec'),scope)
    class Response:
        def __init__(self,path): self.path=path; self.wfile=io.BytesIO(); self.headers={}
        def _handle_skill_management(self,*args): return False
        def _guard_legacy_skill_http(self,*args): return False
        def send_response(self,status): assert status==200
        def send_header(self,k,v): self.headers[k]=v
        def end_headers(self): pass
        def send_json(self,*args): pytest.fail(str(args))
        def send_error(self,*args): pytest.fail(str(args))
    for path in ['/','/index.html','/dist/frontend/index.html','/dist/frontend/index.classic.html']:
        response=Response(path); scope['do_GET'](response); data=response.wfile.getvalue()
        assert f'<title>{title}</title>'.encode() in data
        assert f'<span id="productName">{title}</span>'.encode() in data
        assert f'data-instance-mode="{mode}"'.encode() in data
        assert int(response.headers['Content-Length'])==len(data)
