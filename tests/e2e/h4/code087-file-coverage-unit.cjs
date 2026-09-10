const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const start = app.indexOf('function formatFileCoverage(result)');
const resultStart = app.indexOf('function formatToolResult(result)');
const end = app.indexOf('\nfunction ', resultStart + 1);
assert(start >= 0 && end > resultStart);
const outcomes = [];
for (const language of ['zh', 'en']) {
  const context = vm.createContext({window: {}, formatSize: n => `${n} B`, _safeMd: text => text});
  for (const source of ['src/core/namespace.js', 'src/core/i18n.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, source), 'utf8'), context);
  }
  context.t = (key, params) => context.window.Code.core.i18n.translate(key, params, language);
  vm.runInContext(app.slice(start, end), context);
  const format = result => context.formatToolResult(result);
  for (const [action, extra] of [['list_files', {items:[]}], ['search_files', {results:[],query:'NEEDLE'}], ['glob_files', {results:[],pattern:'*.txt'}]]) {
    const old = {ok:true,action,count:0,truncated:false,...extra};
    const before = JSON.stringify(old);
    const complete = {...old,coverage:{status:'complete',reasons:{},scope:{rootFallback:false}}};
    const partial = {...old,coverage:{status:'partial',reasons:{file_unreadable:2},scope:{rootFallback:false}}};
    assert(format(complete).includes(context.t('fmtCoverageComplete')));
    assert(format(partial).includes(context.t('fmtCoverageNoPartialMatch')));
    assert(!format(old).includes(context.t('fmtCoverageComplete')));
    assert.equal(JSON.stringify(old),before);
    const failed = {...partial,ok:false,error:'Target is not accessible for this operation.',coverage:{status:'failed',reasons:{directory_unavailable:1}}};
    assert(format(failed).includes(context.t('fmtCoverageFailed')));
    if(language === 'zh') assert(!format(failed).includes('Target is not accessible'));
    outcomes.push({language,action,oldUnchanged:true,complete:true,partial:true,failed:true});
  }
  for(const action of ['list_files','glob_files']) {
    const key = action === 'list_files' ? 'items' : 'results';
    const entries = Array.from({length:25},(_,i)=>({type:'file',path:`unknown-${i}.txt`,size:0,sizeAvailable:false}));
    const text = format({ok:true,action,count:25,[key]:entries,coverage:{status:'partial',reasons:{metadata_unavailable:25}}});
    assert.equal(text.split(context.t('fmtSizeUnknown')).length-1,25);
    assert(!text.includes('0 B'));
  }
  const fallback = format({ok:true,action:'glob_files',pattern:'*.txt',count:1,results:[{type:'file',path:'outside.txt',size:10}],coverage:{status:'partial',reasons:{directory_unavailable:1},scope:{rootFallback:true,requestedPath:'sub'}}});
  assert(fallback.includes(context.t('fmtCoverageFallback',{path:'sub'})));
}
console.log(JSON.stringify({ok:true,outcomes},null,2));
