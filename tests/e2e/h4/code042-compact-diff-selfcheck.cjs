const assert = require('node:assert/strict');
global.window = {Code:{ui:{}}};
require('../../../src/ui/diff.js');
const {compactUnifiedDiff:parse,createDiffFeature} = window.Code.ui.diff;
const checks=[];
function check(name,fn){fn();checks.push(name);}
const header='--- a/sample.js\n+++ b/sample.js\n';
const multi=header+'@@ -1,12 +1,13 @@\n one\n two\n-old3\n+new3\n+extra\n four\n five\n six\n seven\n eight\n-old9\n+new9\n ten\n eleven\n twelve\n@@ -20,3 +21,3 @@\n twenty\n-old21\n+new21\n twentyTwo\n';
check('multihunk real offsets and exact omitted intervals',()=>{
 const result=parse(multi);assert(result.ok);
 assert.deepEqual(result.rows.filter(r=>r.kind==='gap').map(r=>r.count),[1,3,9]);
 assert.deepEqual(result.rows.filter(r=>r.kind==='add').map(r=>r.newLine),[3,4,10,22]);
 assert.deepEqual(result.rows.filter(r=>r.kind==='remove').map(r=>r.oldLine),[3,9,21]);
 assert(!result.rows.some(r=>r.text==='one'||r.text==='five'));
});
check('adjacent context windows merge without duplicate lines',()=>{
 const result=parse('@@ -1,5 +1,5 @@\n a\n-b\n+B\n c\n-d\n+D\n e');
 assert(result.ok);assert.equal(result.rows.filter(r=>r.kind==='context').length,3);assert.equal(result.rows.filter(r=>r.kind==='gap').length,0);
});
check('new deleted empty and insertion anchor numbering',()=>{
 const added=parse(header+'@@ -0,0 +1,2 @@\n+a\n+b');assert(added.ok);assert.deepEqual(added.rows.map(r=>r.newLine),[1,2]);
 const deleted=parse(header+'@@ -1,2 +0,0 @@\n-a\n-b');assert(deleted.ok);assert.deepEqual(deleted.rows.map(r=>r.oldLine),[1,2]);
 assert.deepEqual(parse(header).rows,[]);assert.deepEqual(parse('').rows,[]);
 assert.deepEqual(parse('@@ -1,3 +1,3 @@\n a\n b\n c').rows,[]);
 const middle=parse('@@ -5,0 +6 @@\n+new');assert(middle.ok);assert.equal(middle.rows[0].count,5);assert.equal(middle.rows[1].newLine,6);
});
check('source metadata prefixes and no-newline marker are not swallowed',()=>{
 const result=parse('@@ -1,2 +1,2 @@\n---- source\n-@@ old\n++++ source\n+@@ new\n\\ No newline at end of file');
 assert(result.ok);assert.deepEqual(result.rows.map(r=>r.text),['--- source','@@ old','+++ source','@@ new']);assert(result.rows.at(-1).noNewline);
});
check('malformed counts overlapping hunks and multiple files use raw fallback',()=>{
 for(const source of ['@@ -1,2 +1 @@\n-a\n+b','@@ -1 +1 @@\n-a\n+b\n@@ -1 +1 @@\n-c\n+d',header+'@@ -1 +1 @@\n-a\n+b\n'+header+'@@ -1 +1 @@\n-c\n+d','@@ -0 +1 @@\n-a\n+b','@@ -9007199254740992 +1 @@\n-a\n+b','\\ No newline at end of file','+raw'])assert.equal(parse(source).ok,false,source);
});
check('unknown gap has no fabricated count and fenced CRLF parses',()=>{
 assert.equal(parse('@@ -3 +5 @@\n-a\n+b').rows[0].count,null);
 assert(parse('```diff\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n```').ok);
 assert.equal(parse('+'.repeat(1048577)).ok,false);
});
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const copies=[];const feature=createDiffFeature({escapeHtml:escape,t:(key,args)=>key+JSON.stringify(args||{}),renderCopyButton:value=>{copies.push(value);return '<copy/>';},isEditDiffExpanded:()=>true});
check('compact safe HTML keeps metadata hidden and raw fallback escaped',()=>{
 const html=feature.renderDiff(multi,{compact:true,expanded:true});assert(!html.includes('@@'));assert(!html.includes('--- a/'));assert(html.includes('data-new-line="22"'));assert(html.includes('data-omitted-lines="9"'));
 const malicious=feature.renderDiff('@@ -1 +1 @@\n-<img src=x onerror=alert(1)>\n+<script>x()</script>',{compact:true});assert(!malicious.includes('<script>'));assert(!malicious.includes('<img '));assert(malicious.includes('&lt;script&gt;'));
 const raw=feature.renderDiff('<img src=x>\n@@ bad',{compact:true});assert(raw.includes('compactDiffFallback'));assert(!raw.includes('<img '));assert(!raw.includes('diff-num'));
});
check('ordinary proposal states raw copy payload and approval controls unchanged',()=>{
 for(const meta of [{},{applied:true},{outcome:'failed'},{serverManaged:true,authorizationId:'a',authorizationDecision:'approved'}]){
  const msg={role:'tool-result',content:multi,meta:{pendingEditId:'p',action:'propose_edit',path:'/test.js',...meta}},before=JSON.stringify(msg);
  const html=feature.renderEditSuggestionProjection(msg,0);assert(html.includes('compact-diff'));assert.equal(JSON.stringify(msg),before);assert.equal(copies.at(-1),multi.trim());
  assert.equal(html.includes('class="apply-edit-btn"'),Object.keys(meta).length===0);
  if(meta.applied)assert(html.includes('is-applied'));if(meta.outcome)assert(html.includes('is-rejected'));
 }
});
check('long valid changes and legacy raw write retain bounded disclosure',()=>{
 const source='@@ -0,0 +1,50 @@\n'+Array(50).fill('+new').join('\n');
 assert(feature.renderDiff(source,{compact:true}).includes('is-collapsed'));assert(feature.renderDiff(source,{compact:true,expanded:true}).includes('is-expanded'));
 const raw=Array(50).fill('<script>raw</script>').join('\n');
 const html=feature.renderEditSuggestionProjection({role:'tool-result',content:raw,meta:{pendingEditId:'w',action:'write_file'}},0);
 assert(html.includes('write-file-preview is-collapsed'));assert(!html.includes('<script>'));assert.equal(copies.at(-1),raw);assert(html.includes('data-edit-id="w"'));
});
console.log(JSON.stringify({ok:true,checks}));
