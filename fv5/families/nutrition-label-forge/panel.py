#!/usr/bin/env python3
"""The calculator, the exemption checker and the panel drawing, as one bundle.

The free family page and the paid private page run the SAME code. The only
differences are a flag: the free page stamps DRAFT across the drawing and hides
the download buttons; the paid page does not stamp it, adds the downloads, and
picks up a recipe the free page saved in this browser and then wipes that copy.

Everything is inline. The site publishes only HTML pages, so there is no
`app.js` and no `data.json` to fetch -- the food table, the rounding rules and
the quoted regulation all ship inside the page as one JSON island.

Two rules are wired into the code rather than into the wording, because wording
can be edited and code has to be edited on purpose:

  * `panel_rows()` has no branch that writes an ingredient statement or an
    allergen line. Those two strings only ever come from a textarea the buyer
    typed into, and they are copied through unchanged.
  * nothing here prints a sentence about whether the buyer is exempt, or whether
    a label passes. The exemption tool prints the paragraph of the regulation
    each answer touches and stops there.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# Helvetica first, as the brief asks; the rest are the fonts that actually exist
# on Linux and Windows boxes so the drawing does not fall back to a serif.
FONT_STACK = ("Helvetica, 'Helvetica Neue', Arial, 'Liberation Sans', "
              "'Nimbus Sans', sans-serif")

STORAGE_KEY = "fv6.nutrition-label-forge.recipe"


def load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def data_blob(paid: bool, product_name: str = "") -> dict:
    """The JSON island the page carries. Foods dominate it: about 330 KB."""
    foods = load("foods")
    rounding = load("rounding")
    dv = load("dv")
    rules = load("rules")
    cites = load("citations")
    status = load("status")
    by_key = {c["key"]: c for c in cites}
    keep = ["required", "round-calories", "round-fat", "round-sat", "round-trans",
            "round-chol", "round-sodium", "round-carb", "round-fiber",
            "round-sugars", "round-added-sugars", "round-protein",
            "vitamins-order", "vitamin-percent", "insignificant", "serving-rules",
            "serving-household", "servings-per", "type-size", "racc-principle",
            "racc-basis", "ingredients-order", "fdc-licence"]
    return {
        "paid": bool(paid),
        "product": product_name or "",
        "key": STORAGE_KEY,
        "stamp": status["date"],
        "drift": status["drift"],
        "drifted": status["drifted"],
        "edition": status["ecfr_edition"],
        "f": foods,
        "r": rounding,
        "dv": dv,
        "ex": {"questions": rules["questions"], "paras": rules["exemptions"]},
        "c": {k: by_key[k] for k in keep if k in by_key},
    }


# The nine major food allergens named by the Food Allergen Labeling and Consumer
# Protection Act as amended, shown to the buyer as a reminder list. The tool
# never ticks any of them for the buyer and never reads the recipe to guess.
BIG_NINE = ["Milk", "Eggs", "Fish", "Crustacean shellfish", "Tree nuts",
            "Peanuts", "Wheat", "Soybeans", "Sesame"]


def css() -> str:
    return """
<style>
.nlf{--ink:#111;--line:#c9c9c9;--soft:#f6f6f4;--warn:#8a3b00;
 font-size:15px;line-height:1.5;max-width:62rem}
.nlf h3{margin:1.6rem 0 .3rem;font-size:1.15rem}
.nlf h4{margin:1.1rem 0 .3rem;font-size:1rem}
.nlf p.help{color:#555;margin:.2rem 0 .6rem}
.nlf fieldset{border:1px solid var(--line);border-radius:6px;margin:0 0 .6rem;padding:.6rem .8rem}
.nlf legend{padding:0 .35rem;font-weight:600}
.nlf .q{display:block;padding:.35rem 0;border-bottom:1px solid #eee}
.nlf .q:last-child{border-bottom:0}
.nlf .q .ask{display:block;margin-bottom:.2rem}
.nlf .q .opts label{margin-right:1rem;font-size:.92rem}
.nlf .row{display:flex;flex-wrap:wrap;gap:.5rem;align-items:flex-end;margin:.35rem 0}
.nlf .row label{display:flex;flex-direction:column;font-size:.85rem;color:#444;gap:.15rem}
.nlf input[type=text],.nlf input[type=number],.nlf input[type=search],.nlf textarea,.nlf select{
 font:inherit;padding:.35rem .45rem;border:1px solid #aaa;border-radius:4px;background:#fff;color:var(--ink)}
.nlf input[type=number]{width:7rem}
.nlf textarea{width:100%;min-height:5.5rem}
.nlf table.ing{width:100%;border-collapse:collapse;margin:.4rem 0}
.nlf table.ing th,.nlf table.ing td{border-bottom:1px solid var(--line);padding:.3rem .35rem;text-align:left;font-size:.9rem;vertical-align:top}
.nlf table.ing td.g{width:6.5rem}
.nlf table.ing td.x{width:2.5rem;text-align:right}
.nlf button{font:inherit;padding:.4rem .7rem;border:1px solid #333;border-radius:4px;background:#fff;cursor:pointer}
.nlf button.go{background:#111;color:#fff}
.nlf button.lnk{border:0;background:none;text-decoration:underline;padding:.1rem .2rem;cursor:pointer}
.nlf .out{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:.7rem .9rem;margin:.6rem 0}
.nlf .out blockquote{margin:.35rem 0 .6rem;padding-left:.7rem;border-left:3px solid #bbb;font-size:.9rem;color:#333}
.nlf .err{color:var(--warn);font-weight:600}
.nlf .hits{list-style:none;margin:.2rem 0;padding:0;max-height:13rem;overflow:auto;border:1px solid var(--line);border-radius:4px}
.nlf .hits li{padding:.25rem .45rem;border-bottom:1px solid #eee;cursor:pointer;font-size:.88rem}
.nlf .hits li:hover{background:#eef}
.nlf .panelwrap{display:flex;gap:1.2rem;flex-wrap:wrap;align-items:flex-start}
.nlf .panelbox{background:#fff;border:1px solid var(--line);padding:.6rem;overflow-x:auto;max-width:100%}
.nlf .fmt button[aria-pressed=true]{background:#111;color:#fff}
.nlf .cite{font-size:.82rem;color:#555;margin:.25rem 0}
.nlf .cite code{font-size:.82rem}
.nlf .warnbox{border:1px solid var(--warn);border-left-width:5px;border-radius:4px;padding:.6rem .8rem;margin:.7rem 0;background:#fff8f2}
@media print{
 @page{size:auto;margin:12mm}
 body *{visibility:hidden}
 #nlf-print,#nlf-print *{visibility:visible}
 #nlf-print{position:absolute;left:0;top:0}
}
#nlf-print{display:none}
</style>
"""


def _skeleton(paid: bool, product_name: str) -> str:
    qs = ""
    who = product_name or "your product"
    allerg = ", ".join(BIG_NINE)
    dl = ""
    if paid:
        dl = """
  <h4>Download the drawings</h4>
  <p class="help">Each button saves a true vector SVG file. Every piece of text in
  it carries its own font size in points, so a printer can open it and check the
  sizes without measuring pixels. Open the file in Illustrator, Inkscape,
  Affinity or a browser.</p>
  <div class="row">
   <button type="button" id="dl-vertical">Vertical panel (SVG)</button>
   <button type="button" id="dl-tabular">Tabular panel (SVG)</button>
   <button type="button" id="dl-linear">Linear panel (SVG)</button>
   <button type="button" id="dl-json">Recipe and typed text (JSON)</button>
   <button type="button" id="print">Print or save as PDF</button>
  </div>
  <p class="help">Printing goes through your browser's own print dialogue with the
  page size left to the printer. Check the printed width with a ruler before you
  order a run: browsers and printers both scale, and the sizes in 21 CFR 101.9(d)
  are sizes on the finished package.</p>
"""
    return """
<div id="nlf" class="nlf" data-paid=\"""" + ("1" if paid else "0") + """\">

 <h3 id="checker">Does this product need a Nutrition Facts panel?</h3>
 <p class="help">Answer what you know. Every yes prints the paragraph of
 21 CFR 101.9(j) that your answer touches, word for word, so you can read the
 rule yourself. This tool does not tell you whether an exemption applies, and it does
 not keep your answers.</p>
 <form id="exform"></form>
 <div class="row">
  <button type="button" class="go" id="exgo">Show the rules my answers touch</button>
  <button type="button" class="lnk" id="exclear">Clear</button>
 </div>
 <div class="out" id="exout" hidden></div>

 <h3 id="calc">Recipe calculator</h3>
 <p class="help">Type your recipe in grams. The numbers per 100 grams come from
 USDA FoodData Central, which is a public database of measured foods, not a
 measurement of your product.</p>

 <fieldset>
  <legend>Ingredients</legend>
  <div class="row">
   <label style="flex:1;min-width:16rem">Search the food table
    <input type="search" id="q" placeholder="butter, rolled oats, honey" autocomplete="off">
   </label>
  </div>
  <ul class="hits" id="hits" hidden></ul>
  <table class="ing"><thead><tr>
    <th>Ingredient</th><th>Grams in the batch</th><th></th>
   </tr></thead><tbody id="ingbody"></tbody></table>
  <p class="help" id="ingnote">No ingredients yet.</p>
 </fieldset>

 <fieldset>
  <legend>Batch and serving</legend>
  <div class="row">
   <label>Finished batch weight (g)
    <input type="number" id="yield" min="0" step="0.1" placeholder="e.g. 900">
   </label>
   <label>Servings per container
    <input type="number" id="servings" min="0" step="0.5" placeholder="e.g. 18">
   </label>
   <label>Serving size (g)
    <input type="number" id="servg" min="0" step="0.1" placeholder="e.g. 50">
   </label>
   <label style="min-width:14rem">Household measure
    <input type="text" id="house" placeholder="1/2 cup" maxlength="40">
   </label>
  </div>
  <p class="help">The finished batch weight is what the batch weighs after
  cooking, not the sum of the raw ingredients. Water lost in the oven changes
  every number on the panel. If you leave it blank the calculator uses the sum of
  the raw weights and says so.</p>
  <div class="row">
   <label>Added sugars in the whole batch (g)
    <input type="number" id="addsug" min="0" step="0.1" value="0">
   </label>
  </div>
  <p class="help">Added sugars is a number you have to supply. Not one row in the
  USDA data this page carries has an added-sugars figure, so there is nothing to
  read it from. Count the sugars, syrups, honey and concentrated juices you put
  in. 21 CFR 101.9(g)(10) requires written records behind this figure.</p>
 </fieldset>

 <fieldset>
  <legend>Ingredient statement and allergens &mdash; you type these</legend>
  <p class="help">This tool does not write either of these lines and never will.
  An ingredient list has to be in descending order of weight as it went into the
  batch, using the names 21 CFR 101.4 allows, including the sub-ingredients of
  compound ingredients. An allergen line has to reflect what is actually in your
  plant. A generated one that misses an allergen is dangerous.</p>
  <label style="display:block">Ingredient statement
   <textarea id="ingstate" placeholder="INGREDIENTS: ROLLED OATS, HONEY, ..."></textarea>
  </label>
  <label style="display:block;margin-top:.5rem">Allergen statement
   <textarea id="allerg" placeholder="CONTAINS: WHEAT, TREE NUTS (ALMONDS)." style="min-height:3.5rem"></textarea>
  </label>
  <p class="help">The nine major food allergens to consider: """ + allerg + """.</p>
  <label style="display:block;margin-top:.4rem;font-size:.92rem">
   <input type="checkbox" id="confirm"> I confirm this list is complete and in
   descending order of weight.
  </label>
 </fieldset>

 <div class="row">
  <button type="button" class="go" id="calcgo">Calculate and draw the panel</button>
  <button type="button" id="demo">Load the granola example</button>
 </div>
 <div id="calcerr" class="warnbox" hidden></div>

 <h3 id="panel">The panel</h3>
 <div class="row fmt" id="fmt">
  <button type="button" data-fmt="vertical" aria-pressed="true">Vertical</button>
  <button type="button" data-fmt="tabular" aria-pressed="false">Tabular</button>
  <button type="button" data-fmt="linear" aria-pressed="false">Linear</button>
 </div>
 <div class="panelwrap">
  <div class="panelbox" id="panelbox"><p class="help">Nothing drawn yet.</p></div>
  <div style="flex:1;min-width:18rem">
   <h4>What the calculator did</h4>
   <div id="workings"><p class="help">Run the calculator to see every step.</p></div>
  </div>
 </div>
""" + dl + """
 <h4>Keep this recipe</h4>
 <p class="help">Saving puts the recipe in this browser only. It never reaches us
 and it is not a backup: browsers clear stored data on their own, and clearing
 site data or using a private window loses it. Export the file if you want to
 keep it.</p>
 <div class="row">
  <label style="font-size:.92rem"><input type="checkbox" id="lockit"> Lock it with
   a passphrase before saving</label>
 </div>
 <div class="row">
  <button type="button" id="save">Save in this browser</button>
  <button type="button" id="load">Load from this browser</button>
  <button type="button" id="export">Export a file</button>
  <button type="button" id="importbtn">Import a file</button>
  <input type="file" id="importfile" accept="application/json" hidden>
  <button type="button" class="lnk" id="forget">Forget the saved copy</button>
 </div>
 <p class="help" id="storenote"></p>
</div>
<div id="nlf-print"></div>
"""


def js() -> str:
    return r"""
<script>
(function(){
 var D=JSON.parse(document.getElementById('nlf-data').textContent);
 var root=document.getElementById('nlf');
 if(!root) return;
 var PAID=root.getAttribute('data-paid')==='1';
 var $=function(id){return document.getElementById(id);};
 var esc=function(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
   return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};

 /* ---------- the food table ------------------------------------------- */
 var F=D.f, KEYS=F.keys, SCALE=F.scale;
 var IDX=F.foods.map(function(r,i){return {i:i,l:r[3].toLowerCase()};});
 function search(q){
  q=q.trim().toLowerCase(); if(q.length<2) return [];
  var parts=q.split(/\s+/), out=[];
  for(var k=0;k<IDX.length;k++){
   var l=IDX[k].l, ok=true;
   for(var p=0;p<parts.length;p++){ if(l.indexOf(parts[p])<0){ok=false;break;} }
   if(ok) out.push(IDX[k].i);
   if(out.length>200) break;
  }
  out.sort(function(a,b){
   var da=F.foods[a][3].toLowerCase(), db=F.foods[b][3].toLowerCase();
   var sa=da.indexOf(parts[0])===0?0:1, sb=db.indexOf(parts[0])===0?0:1;
   if(sa!==sb) return sa-sb;
   if(da.length!==db.length) return da.length-db.length;
   return da<db?-1:1;});
  return out.slice(0,40);
 }
 function val(row,key){var j=KEYS.indexOf(key); return j<0?0:row[4][j]/SCALE;}

 /* ---------- rounding, straight off data/rounding.json ----------------- */
 var RULES={}; D.r.rules.forEach(function(r){RULES[r.key]=r;});
 function dec(step){var s=String(step); var d=s.indexOf('.'); return d<0?0:s.length-d-1;}
 function snap(v,step){
  var n=Math.round(v/step)*step;
  /* A half-gram step prints "0.5g" but a whole number prints "1g", not "1.0g":
     the increment is what the rule fixes, not the number of decimals shown. */
  var t=n.toFixed(dec(step));
  if(t.indexOf('.')>0) t=t.replace(/\.?0+$/,'');
  if(t==='' || t==='-0') t='0';
  return {n:n,t:t};
 }
 function applyRule(key,v){
  var rule=RULES[key]; if(!rule) return {n:v,t:String(v)};
  for(var i=0;i<rule.rule.length;i++){
   var s=rule.rule[i];
   if(s.below!==undefined && !(v<s.below)) continue;
   if(s.to==='zero') return {n:0,t:'0'};
   if(s.to==='less-than-1') return {n:v,t:'<1',lt:1};
   if(s.to==='less-than-5') return {n:v,t:'<5',lt:5};
   return snap(v,s.step);
  }
  return {n:v,t:String(v)};
 }
 /* % Daily Value. Macronutrients go to the nearest whole percent, as
    101.9(d)(7)(ii) says. Vitamins and minerals go in 2, 5 and 10 point steps,
    as 101.9(c)(8)(iii) says. Both are computed from the ROUNDED amount that
    the panel prints, which is what (d)(7)(ii) tells you to divide. */
 var VITS={vitd:1,ca:1,fe:1,k:1};
 function pct(key,amount){
  var d=D.dv.values[key]; if(!d) return null;
  var raw=amount/d.dv*100;
  if(VITS[key]){
   if(raw<=10) return Math.round(raw/2)*2;
   if(raw<=50) return Math.round(raw/5)*5;
   return Math.round(raw/10)*10;
  }
  return Math.round(raw);
 }

 /* ---------- the recipe ------------------------------------------------ */
 var recipe={items:[],yield_g:null,servings:null,serving_g:null,house:'',
             added_sugars_g:0,ingredient_statement:'',allergen_statement:'',
             confirmed:false,product:D.product||''};

 function drawItems(){
  var tb=$('ingbody'); tb.innerHTML='';
  recipe.items.forEach(function(it,n){
   var tr=document.createElement('tr');
   tr.innerHTML='<td>'+esc(it.desc)+'</td>'+
     '<td class="g"><input type="number" min="0" step="0.1" value="'+it.g+'" data-n="'+n+'"></td>'+
     '<td class="x"><button type="button" class="lnk" data-del="'+n+'">remove</button></td>';
   tb.appendChild(tr);
  });
  $('ingnote').textContent=recipe.items.length?
    (recipe.items.length+' ingredient'+(recipe.items.length===1?'':'s')+', '+
     recipe.items.reduce(function(a,b){return a+(+b.g||0);},0).toFixed(1)+' g raw.'):
    'No ingredients yet.';
  tb.querySelectorAll('input').forEach(function(inp){
   inp.addEventListener('input',function(){recipe.items[+inp.dataset.n].g=+inp.value||0; drawItems();});
  });
  tb.querySelectorAll('[data-del]').forEach(function(b){
   b.addEventListener('click',function(){recipe.items.splice(+b.dataset.del,1); drawItems();});
  });
 }
 function addFood(i,g){
  var r=F.foods[i];
  recipe.items.push({fdc:r[0],desc:r[3],g:g||0,
    per100:KEYS.reduce(function(o,k,j){o[k]=r[4][j]/SCALE;return o;},{})});
  drawItems();
 }
 $('q').addEventListener('input',function(){
  var hits=search(this.value), ul=$('hits');
  if(!hits.length){ul.hidden=true;ul.innerHTML='';return;}
  ul.innerHTML=hits.map(function(i){
    return '<li data-i="'+i+'">'+esc(F.foods[i][3])+' <span style="color:#777">&middot; '+
      esc(F.cats[F.foods[i][1]])+'</span></li>';}).join('');
  ul.hidden=false;
  ul.querySelectorAll('li').forEach(function(li){
   li.addEventListener('click',function(){
    addFood(+li.dataset.i,0); $('q').value=''; ul.hidden=true; ul.innerHTML='';});
  });
 });

 /* ---------- read the form -------------------------------------------- */
 function readForm(){
  recipe.yield_g=$('yield').value===''?null:+$('yield').value;
  recipe.servings=$('servings').value===''?null:+$('servings').value;
  recipe.serving_g=$('servg').value===''?null:+$('servg').value;
  recipe.house=$('house').value.trim();
  recipe.added_sugars_g=+$('addsug').value||0;
  recipe.ingredient_statement=$('ingstate').value;
  recipe.allergen_statement=$('allerg').value;
  recipe.confirmed=$('confirm').checked;
 }
 function writeForm(){
  $('yield').value=recipe.yield_g==null?'':recipe.yield_g;
  $('servings').value=recipe.servings==null?'':recipe.servings;
  $('servg').value=recipe.serving_g==null?'':recipe.serving_g;
  $('house').value=recipe.house||'';
  $('addsug').value=recipe.added_sugars_g||0;
  $('ingstate').value=recipe.ingredient_statement||'';
  $('allerg').value=recipe.allergen_statement||'';
  $('confirm').checked=!!recipe.confirmed;
  drawItems();
 }

 /* ---------- the sums -------------------------------------------------- */
 var ORDER=[
  {k:'fat',  name:'Total Fat', unit:'g', bold:true, ind:0},
  {k:'sat',  name:'Saturated Fat', unit:'g', bold:false, ind:1},
  {k:'trans',name:'Trans Fat', unit:'g', bold:false, ind:1, italic:'Trans'},
  {k:'chol', name:'Cholesterol', unit:'mg', bold:true, ind:0},
  {k:'na',   name:'Sodium', unit:'mg', bold:true, ind:0},
  {k:'carb', name:'Total Carbohydrate', unit:'g', bold:true, ind:0},
  {k:'fib',  name:'Dietary Fiber', unit:'g', bold:false, ind:1},
  {k:'sug',  name:'Total Sugars', unit:'g', bold:false, ind:1},
  {k:'addsug',name:'Includes Added Sugars', unit:'g', bold:false, ind:2},
  {k:'prot', name:'Protein', unit:'g', bold:true, ind:0}
 ];
 var VITROWS=[{k:'vitd',name:'Vitamin D',unit:'mcg'},{k:'ca',name:'Calcium',unit:'mg'},
              {k:'fe',name:'Iron',unit:'mg'},{k:'k',name:'Potassium',unit:'mg'}];

 function compute(){
  var errs=[];
  if(!recipe.items.length) errs.push('Add at least one ingredient.');
  var raw=recipe.items.reduce(function(a,b){return a+(+b.g||0);},0);
  if(raw<=0) errs.push('Give every ingredient a weight in grams above zero.');
  var yld=recipe.yield_g;
  var usedRaw=false;
  if(yld==null||yld<=0){ yld=raw; usedRaw=true; }
  if(!(recipe.servings>0)) errs.push('Servings per container has to be a number above zero.');
  if(!(recipe.serving_g>0)) errs.push('Serving size in grams has to be a number above zero.');
  if(errs.length) return {ok:false,errs:errs};
  if(recipe.serving_g>yld) errs.push('One serving weighs more than the whole batch.');
  if(errs.length) return {ok:false,errs:errs};

  var totals={};
  KEYS.forEach(function(k){
   totals[k]=recipe.items.reduce(function(a,it){return a+(it.per100[k]||0)*(+it.g||0)/100;},0);
  });
  totals.addsug=+recipe.added_sugars_g||0;
  var share=recipe.serving_g/yld;
  var per={}, rounded={}, dvs={};
  Object.keys(totals).forEach(function(k){
   per[k]=totals[k]*share;
   rounded[k]=applyRule(k,per[k]);
   dvs[k]=D.dv.values[k]?pct(k,rounded[k].lt?0:rounded[k].n):null;
  });
  return {ok:true,raw:raw,yield_g:yld,usedRaw:usedRaw,share:share,
          totals:totals,per:per,r:rounded,dv:dvs};
 }

 /* ---------- drawing --------------------------------------------------- */
 var FONT="Helvetica, 'Helvetica Neue', Arial, 'Liberation Sans', 'Nimbus Sans', sans-serif";
 var mc=document.createElement('canvas').getContext('2d');
 function tw(t,pt,w){ mc.font=(w?w+' ':'')+pt+'pt Helvetica, Arial, sans-serif';
   return mc.measureText(String(t)).width/(96/72); }
 function wrap(t,pt,width,w){
  var words=String(t).split(' '), lines=[], cur='';
  for(var i=0;i<words.length;i++){
   var next=cur?cur+' '+words[i]:words[i];
   if(tw(next,pt,w)>width && cur){ lines.push(cur); cur=words[i]; } else cur=next;
  }
  if(cur) lines.push(cur);
  return lines;
 }
 function T(s,x,y,pt,weight,anchor,extra){
  return '<text x="'+x.toFixed(2)+'" y="'+y.toFixed(2)+'" font-size="'+pt+'pt"'+
   ' font-family="'+FONT.replace(/"/g,'&quot;')+'"'+
   (weight?' font-weight="'+weight+'"':'')+
   (anchor?' xml:space="preserve" text-anchor="'+anchor+'"':' xml:space="preserve"')+
   (extra||'')+'>'+esc(s)+'</text>';
 }
 function R(x,y,w,h){ return '<rect x="'+x.toFixed(2)+'" y="'+y.toFixed(2)+
   '" width="'+w.toFixed(2)+'" height="'+h.toFixed(2)+'" fill="#000"/>'; }

 function amountText(row,c){
  var r=c.r[row.k];
  if(row.k==='addsug') return 'Includes ' + r.t + 'g Added Sugars';
  return r.t + row.unit;
 }
 function nameText(row){ return row.k==='addsug'?'':row.name; }

 function svgVertical(c,opts){
  var W=200, PAD=6, x0=PAD, x1=W-PAD, y=0, g=[];
  var lead=function(n){y+=n;};
  lead(26); g.push(T('Nutrition Facts',x0,y,24,'900'));
  lead(4); g.push(R(x0,y,x1-x0,0.8)); lead(3);
  lead(10); g.push(T((c.servingsTxt)+' servings per container',x0,y,9));
  lead(13); g.push(T('Serving size',x0,y,11,'700'));
             g.push(T(c.servingTxt,x1,y,11,'700','end'));
  lead(4); g.push(R(x0,y,x1-x0,8)); lead(9);
  lead(9); g.push(T('Amount per serving',x0,y,8,'700'));
  lead(22); g.push(T('Calories',x0,y,18,'900'));
            g.push(T(c.r.kcal.t,x1,y,26,'900','end'));
  lead(4); g.push(R(x0,y,x1-x0,4)); lead(5);
  lead(9); g.push(T('% Daily Value*',x1,y,8,'700','end'));
  lead(3); g.push(R(x0,y,x1-x0,0.6)); lead(2);
  ORDER.forEach(function(row){
   if(row.k==='addsug' && !(c.r.addsug.n>0) && c.per.addsug===0){ /* still shown: required */ }
   lead(11);
   var ind=row.ind*9;
   var label=nameText(row), amt=amountText(row,c);
   if(row.k==='addsug'){
    g.push(T(amt,x0+ind,y,9));
   } else {
    g.push(T(label,x0+ind,y,9,row.bold?'700':null));
    g.push(T(' '+amt,x0+ind+tw(label,9,row.bold?'bold':null)+1.5,y,9));
   }
   var p=c.dv[row.k];
   if(p!==null&&p!==undefined&&row.k!=='prot') g.push(T(p+'%',x1,y,9,'700','end'));
   lead(3); g.push(R(x0,y,x1-x0,0.6)); lead(1);
  });
  y-=4; g.push(R(x0,y,x1-x0,8)); lead(9);
  VITROWS.forEach(function(row){
   lead(11);
   g.push(T(row.name,x0,y,9));
   g.push(T(' '+c.r[row.k].t+row.unit,x0+tw(row.name,9)+1.5,y,9));
   var p=c.dv[row.k];
   if(p!==null&&p!==undefined) g.push(T(p+'%',x1,y,9,'700','end'));
   lead(3); g.push(R(x0,y,x1-x0,0.6)); lead(1);
  });
  y-=4; g.push(R(x0,y,x1-x0,4)); lead(6);
  var foot='*The % Daily Value tells you how much a nutrient in a serving of food '+
   'contributes to a daily diet. 2,000 calories a day is used for general nutrition advice.';
  wrap(foot,8,x1-x0).forEach(function(l){ lead(9.5); g.push(T(l,x0,y,8)); });
  lead(6);
  return frame(W,y,g,opts);
 }

 function svgTabular(c,opts){
  var W=420, PAD=6, y=0, g=[], colw=(W-2*PAD)/2, xL=PAD, xR=PAD+colw+8;
  y+=20; g.push(T('Nutrition Facts',xL,y,16,'900'));
  y+=13; g.push(T(c.servingsTxt+' servings per container',xL,y,9));
  y+=12; g.push(T('Serving size '+c.servingTxt,xL,y,10,'700'));
  y+=6; g.push(R(PAD,y,W-2*PAD,4)); y+=8;
  var yTop=y;
  y+=14; g.push(T('Calories',xL,y,10,'900'));
         g.push(T(c.r.kcal.t,xL+colw-6,y,14,'900','end'));
  y+=4; g.push(R(xL,y,colw-6,0.6)); y+=2;
  y+=10; g.push(T('% Daily Value*',xL+colw-6,y,8,'700','end'));
  var yL=y, yR=yTop;
  function col(rows,x,w,yy,vit){
   rows.forEach(function(row){
    yy+=11;
    var ind=(row.ind||0)*8;
    if(row.k==='addsug'){ g.push(T(amountText(row,c),x+ind,yy,8)); }
    else {
     g.push(T(row.name,x+ind,yy,8,row.bold?'700':null));
     g.push(T(' '+(vit?c.r[row.k].t+row.unit:amountText(row,c)),
              x+ind+tw(row.name,8,row.bold?'bold':null)+1.5,yy,8));
    }
    var p=c.dv[row.k];
    if(p!==null&&p!==undefined&&row.k!=='prot') g.push(T(p+'%',x+w,yy,8,'700','end'));
    yy+=2.5; g.push(R(x,yy,w,0.5)); yy+=1;
   });
   return yy;
  }
  yL=col(ORDER.slice(0,6),xL,colw-6,yL,false);
  yR=col(ORDER.slice(6).concat(VITROWS.map(function(v){
     return {k:v.k,name:v.name,unit:v.unit,bold:false,ind:0,vit:true};})),
     xR,colw-6,yR+10,false);
  y=Math.max(yL,yR)+4;
  g.push(R(PAD,y,W-2*PAD,3)); y+=6;
  var foot='*The % Daily Value tells you how much a nutrient in a serving of food '+
   'contributes to a daily diet. 2,000 calories a day is used for general nutrition advice.';
  wrap(foot,8,W-2*PAD).forEach(function(l){ y+=9.5; g.push(T(l,PAD,y,8)); });
  y+=6;
  return frame(W,y,g,opts);
 }

 function svgLinear(c,opts){
  var W=320, PAD=6, y=0, g=[];
  y+=15; g.push(T('Nutrition Facts',PAD,y,12,'900'));
  y+=3; g.push(R(PAD,y,W-2*PAD,2)); y+=4;
  var bits=['Serving size '+c.servingTxt,
            c.servingsTxt+' servings per container',
            'Amount per serving: Calories '+c.r.kcal.t];
  ORDER.forEach(function(row){
   var p=c.dv[row.k], amt=(row.k==='addsug')?('Incl. '+c.r.addsug.t+'g Added Sugars')
        :(row.name+' '+c.r[row.k].t+row.unit);
   bits.push(amt+((p!==null&&p!==undefined&&row.k!=='prot')?(' ('+p+'% DV)'):''));
  });
  VITROWS.forEach(function(row){
   var p=c.dv[row.k];
   bits.push(row.name+' '+c.r[row.k].t+row.unit+((p!==null&&p!==undefined)?(' ('+p+'% DV)'):''));
  });
  bits.push('*The % Daily Value (DV) tells you how much a nutrient in a serving of '+
            'food contributes to a daily diet. 2,000 calories a day is used for '+
            'general nutrition advice.');
  wrap(bits.join(', ').replace(/, \*/,'. *'),8,W-2*PAD).forEach(function(l){
   y+=10; g.push(T(l,PAD,y,8));
  });
  y+=6;
  return frame(W,y,g,opts);
 }

 function frame(W,H,g,opts){
  opts=opts||{};
  var cap=0, head='';
  if(opts.caption){ cap=14; head=T(opts.caption,4,11,8,'700'); }
  var total=H+8+cap;
  var body='<rect x="0.5" y="'+(0.5+cap)+'" width="'+(W-1)+'" height="'+(H+7)+
    '" fill="#fff" stroke="#000" stroke-width="1"/>'+
    '<g transform="translate(0,'+(cap+4)+')">'+g.join('')+'</g>';
  var mark='';
  if(opts.draft){
   mark='<text x="'+(W/2)+'" y="'+((total)/2)+'" font-size="'+Math.round(W/4)+
     'pt" font-family="'+FONT.replace(/"/g,'&quot;')+'" font-weight="700"'+
     ' fill="#c00" fill-opacity="0.16" text-anchor="middle"'+
     ' transform="rotate(-32 '+(W/2)+' '+(total/2)+')">DRAFT</text>';
  }
  return '<svg xmlns="http://www.w3.org/2000/svg" width="'+W+'pt" height="'+
   total.toFixed(1)+'pt" viewBox="0 0 '+W+' '+total.toFixed(1)+'">'+
   '<rect width="100%" height="100%" fill="#fff"/>'+head+body+mark+'</svg>';
 }

 /* ---------- run it ---------------------------------------------------- */
 var last=null, fmt='vertical';
 function servingLabels(c){
  var s=recipe.serving_g;
  c.servingTxt=(recipe.house?recipe.house+' ':'')+'('+(Math.round(s*10)/10)+'g)';
  var n=recipe.servings;
  c.servingsTxt=(n>=2&&n<=5)?(Math.round(n*2)/2):Math.round(n);
  return c;
 }
 function draw(){
  if(!last||!last.ok) return;
  var opts={draft:!PAID};
  if(PAID&&(recipe.product||D.product)) opts.caption=recipe.product||D.product;
  var svg=fmt==='vertical'?svgVertical(last,opts):
          fmt==='tabular'?svgTabular(last,opts):svgLinear(last,opts);
  $('panelbox').innerHTML=svg;
  $('nlf-print').innerHTML=svg+(recipe.ingredient_statement?
    '<p style="font:9pt '+FONT.replace(/"/g,"'")+';max-width:'+
    (fmt==='vertical'?200:420)+'pt">'+esc(recipe.ingredient_statement)+'</p>':'')+
    (recipe.allergen_statement?'<p style="font:bold 9pt '+FONT.replace(/"/g,"'")+
    ';max-width:420pt">'+esc(recipe.allergen_statement)+'</p>':'');
  workings();
 }
 function workings(){
  var c=last, rows=[];
  rows.push(['Raw ingredient weight',c.raw.toFixed(1)+' g']);
  rows.push(['Finished batch weight',c.yield_g.toFixed(1)+' g'+
    (c.usedRaw?' (raw sum used: you left the finished weight blank)':'')]);
  rows.push(['One serving',recipe.serving_g+' g, which is '+
    (c.share*100).toFixed(2)+'% of the batch']);
  rows.push(['Servings per container',String(recipe.servings)]);
  var t='<table class="ing"><thead><tr><th>Nutrient</th><th>Per serving, unrounded</th>'+
   '<th>On the panel</th><th>% DV</th></tr></thead><tbody>';
  [{k:'kcal',n:'Calories',u:''}].concat(ORDER,VITROWS).forEach(function(r){
   var k=r.k;
   t+='<tr><td>'+esc(r.n||r.name)+'</td><td>'+(c.per[k]).toFixed(2)+(r.u===''?'':(r.unit||''))+
     '</td><td>'+esc(c.r[k].t)+(r.u===''?'':(r.unit||''))+'</td><td>'+
     (c.dv[k]==null||k==='prot'?'&mdash;':c.dv[k]+'%')+'</td></tr>';
  });
  t+='</tbody></table>';
  var head=rows.map(function(r){return '<p class="help"><strong>'+esc(r[0])+':</strong> '+
    esc(r[1])+'</p>';}).join('');
  var cites='<p class="cite">Rounding from 21 CFR 101.9(c); Daily Values from the '+
   'tables in 101.9(c)(8)(iv) and (c)(9), edition of '+esc(D.edition)+'. '+
   'Percentages are worked out from the rounded figure the panel prints, as '+
   '101.9(d)(7)(ii) directs. Protein carries no percent here: 101.9(c)(7) makes '+
   'that percent optional unless a protein claim is made or the food is for '+
   'children under 4.</p>';
  $('workings').innerHTML=head+t+cites;
 }

 $('calcgo').addEventListener('click',function(){
  readForm();
  var c=compute();
  if(!c.ok){
   $('calcerr').hidden=false;
   $('calcerr').innerHTML='<p class="err">The panel was not drawn.</p><ul>'+
    c.errs.map(function(e){return '<li>'+esc(e)+'</li>';}).join('')+'</ul>';
   $('panelbox').innerHTML='<p class="help">Nothing drawn yet.</p>';
   $('nlf-print').innerHTML=''; last=null; return;
  }
  $('calcerr').hidden=true;
  last=servingLabels(c);
  draw();
 });
 $('fmt').addEventListener('click',function(e){
  var b=e.target.closest('button[data-fmt]'); if(!b) return;
  fmt=b.dataset.fmt;
  $('fmt').querySelectorAll('button').forEach(function(x){
   x.setAttribute('aria-pressed',x===b?'true':'false');});
  draw();
 });

 /* ---------- the exemption checker ------------------------------------- */
 var PARAS={}; D.ex.paras.forEach(function(p){PARAS[p.para]=p.quote;});
 (function(){
  var f=$('exform');
  f.innerHTML=D.ex.questions.map(function(q,i){
   return '<span class="q"><span class="ask">'+esc(q.ask)+'</span>'+
    '<span class="opts">'+
    '<label><input type="radio" name="ex'+i+'" value="y"> Yes</label>'+
    '<label><input type="radio" name="ex'+i+'" value="n"> No</label>'+
    '<label><input type="radio" name="ex'+i+'" value="?" checked> Not sure</label>'+
    '</span></span>';
  }).join('');
 })();
 $('exgo').addEventListener('click',function(){
  var out=[], seen={};
  D.ex.questions.forEach(function(q,i){
   var sel=document.querySelector('[name=ex'+i+']:checked');
   if(!sel||sel.value!=='y') return;
   out.push('<h4>'+esc(q.ask)+'</h4><p class="cite">'+esc(q.reads)+'</p>');
   q.paras.forEach(function(n){
    var key='(j)('+n+')';
    if(seen[key]) return; seen[key]=1;
    if(PARAS[key]) out.push('<blockquote><strong>21 CFR 101.9'+esc(key)+'</strong> '+
      esc(PARAS[key])+'</blockquote>');
   });
  });
  var box=$('exout'); box.hidden=false;
  if(!out.length){
   box.innerHTML='<p>No answer was set to yes, so there is nothing to quote. '+
    'Set an answer to yes to see the paragraph it touches.</p>';
   return;
  }
  box.innerHTML='<p><strong>The paragraphs your answers touch.</strong> These are '+
   'the words of the regulation as of '+esc(D.edition)+', quoted and trimmed to '+
   'their first 900 characters. They are printed here so you can read them. '+
   'Nothing on this page decides whether any of them applies to your product.</p>'+
   out.join('')+'<p class="cite">Source: '+
   '<a href="https://www.ecfr.gov/current/title-21/section-101.9">'+
   'eCFR, 21 CFR 101.9</a>. The eCFR is not the official legal edition of the CFR.</p>';
 });
 $('exclear').addEventListener('click',function(){
  document.querySelectorAll('[value="?"]').forEach(function(r){r.checked=true;});
  $('exout').hidden=true;
 });

 /* ---------- keeping a recipe ------------------------------------------ */
 var KEY=D.key;
 function note(t){ $('storenote').textContent=t; }
 function plain(){
  readForm();
  return JSON.parse(JSON.stringify({
   v:1, saved:new Date().toISOString(),
   product:recipe.product||D.product||'',
   items:recipe.items, yield_g:recipe.yield_g, servings:recipe.servings,
   serving_g:recipe.serving_g, house:recipe.house,
   added_sugars_g:recipe.added_sugars_g,
   ingredient_statement:recipe.ingredient_statement,
   allergen_statement:recipe.allergen_statement,
   confirmed:recipe.confirmed}));
 }
 function adopt(o){
  recipe.items=(o.items||[]).map(function(it){
   if(it.per100) return it;
   var j=F.foods.findIndex(function(r){return r[0]===it.fdc;});
   return {fdc:it.fdc,desc:it.desc,g:it.g,
     per100:j<0?{}:KEYS.reduce(function(a,k,n){a[k]=F.foods[j][4][n]/SCALE;return a;},{})};
  });
  recipe.yield_g=o.yield_g; recipe.servings=o.servings; recipe.serving_g=o.serving_g;
  recipe.house=o.house||''; recipe.added_sugars_g=o.added_sugars_g||0;
  recipe.ingredient_statement=o.ingredient_statement||'';
  recipe.allergen_statement=o.allergen_statement||'';
  recipe.confirmed=!!o.confirmed;
  if(o.product) recipe.product=o.product;
  writeForm();
 }
 var enc=new TextEncoder(), decd=new TextDecoder();
 function b64(buf){var b='',a=new Uint8Array(buf);
  for(var i=0;i<a.length;i++)b+=String.fromCharCode(a[i]); return btoa(b);}
 function unb64(s){var b=atob(s),a=new Uint8Array(b.length);
  for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i); return a;}
 function keyFrom(pass,salt){
  return crypto.subtle.importKey('raw',enc.encode(pass),'PBKDF2',false,['deriveKey'])
   .then(function(k){return crypto.subtle.deriveKey(
    {name:'PBKDF2',salt:salt,iterations:200000,hash:'SHA-256'},k,
    {name:'AES-GCM',length:256},false,['encrypt','decrypt']);});
 }
 function lockUp(obj,pass){
  var salt=crypto.getRandomValues(new Uint8Array(16));
  var iv=crypto.getRandomValues(new Uint8Array(12));
  return keyFrom(pass,salt).then(function(k){
   return crypto.subtle.encrypt({name:'AES-GCM',iv:iv},k,enc.encode(JSON.stringify(obj)));
  }).then(function(ct){
   return {locked:true,kdf:'PBKDF2-SHA256',iterations:200000,
           salt:b64(salt),iv:b64(iv),data:b64(ct)};
  });
 }
 function unlock(o,pass){
  return keyFrom(pass,unb64(o.salt)).then(function(k){
   return crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(o.iv)},k,unb64(o.data));
  }).then(function(pt){ return JSON.parse(decd.decode(pt)); });
 }
 function store(o){
  try{ localStorage.setItem(KEY,JSON.stringify(o)); return true; }
  catch(e){ note('This browser refused to store it: '+e.name+
    '. Export a file instead.'); return false; }
 }
 $('save').addEventListener('click',function(){
  var body=plain();
  if($('lockit').checked){
   var p=prompt('Passphrase to lock this recipe. There is no way to recover it.');
   if(!p) return;
   lockUp(body,p).then(function(w){ if(store(w))
     note('Saved and locked in this browser at '+new Date().toLocaleString()+
          '. You will be asked for the passphrase to load it.'); })
    .catch(function(e){note('Could not lock it: '+e.message);});
   return;
  }
  if(store(body)) note('Saved in this browser at '+new Date().toLocaleString()+
   '. Not locked, and not a backup.');
 });
 $('load').addEventListener('click',function(){
  var raw; try{ raw=localStorage.getItem(KEY);}catch(e){raw=null;}
  if(!raw){ note('Nothing is saved in this browser under this page.'); return; }
  var o; try{ o=JSON.parse(raw);}catch(e){ note('The saved copy is unreadable.'); return; }
  if(o&&o.locked){
   var p=prompt('Passphrase for the saved recipe.');
   if(!p) return;
   unlock(o,p).then(function(d){adopt(d);note('Loaded and unlocked.');})
    .catch(function(){note('That passphrase did not open it.');});
   return;
  }
  adopt(o); note('Loaded from this browser.');
 });
 $('forget').addEventListener('click',function(){
  try{ localStorage.removeItem(KEY); }catch(e){}
  note('The saved copy is gone from this browser.');
 });
 function download(name,mime,text){
  var a=document.createElement('a');
  a.href='data:'+mime+';charset=utf-8,'+encodeURIComponent(text);
  a.download=name; document.body.appendChild(a); a.click(); a.remove();
 }
 $('export').addEventListener('click',function(){
  download('nutrition-recipe.json','application/json',JSON.stringify(plain(),null,1));
 });
 $('importbtn').addEventListener('click',function(){ $('importfile').click(); });
 $('importfile').addEventListener('change',function(){
  var f=this.files[0]; if(!f) return;
  var rd=new FileReader();
  rd.onload=function(){
   var o; try{o=JSON.parse(rd.result);}catch(e){note('That file is not readable JSON.');return;}
   if(o&&o.locked){
    var p=prompt('Passphrase for this file.'); if(!p) return;
    unlock(o,p).then(function(d){adopt(d);note('Imported and unlocked.');})
     .catch(function(){note('That passphrase did not open it.');});
    return;
   }
   adopt(o); note('Imported.');
  };
  rd.readAsText(f);
 });

 /* ---------- the granola example ---------------------------------------
    Loaded by FoodData Central id, not by searching for a word: a search for
    "oats" also matches "buckwheat groats", and the fixtures state the numbers
    this recipe has to produce, so the rows must be the same rows every time. */
 var DEMO={items:[[173904,400],[169640,120],[171025,80],[170567,100],
                  [170562,60],[173468,3]],
   yield_g:700, servings:14, serving_g:50, house:'1/2 cup', added_sugars_g:97,
   ingredient_statement:'INGREDIENTS: ROLLED OATS, HONEY, SUNFLOWER OIL, '+
     'ALMONDS, SUNFLOWER SEEDS, SALT.',
   allergen_statement:'CONTAINS: TREE NUTS (ALMONDS).'};
 function byId(fdc){
  for(var i=0;i<F.foods.length;i++){ if(F.foods[i][0]===fdc) return i; }
  return -1;
 }
 function loadDemo(){
  recipe.items=[];
  DEMO.items.forEach(function(pair){
   var i=byId(pair[0]);
   if(i>=0) addFood(i,pair[1]);
  });
  recipe.yield_g=DEMO.yield_g; recipe.servings=DEMO.servings;
  recipe.serving_g=DEMO.serving_g; recipe.house=DEMO.house;
  recipe.added_sugars_g=DEMO.added_sugars_g;
  recipe.ingredient_statement=DEMO.ingredient_statement;
  recipe.allergen_statement=DEMO.allergen_statement;
  recipe.confirmed=false;
  writeForm();
  $('calcgo').click();
 }
 $('demo').addEventListener('click',loadDemo);
 window.nlfLoadDemo=loadDemo;
 /* The same door the granola button uses, opened to any recipe of the
    same shape. browser_test.py drives the fixtures through here so the
    numbers the fixtures state are produced by the page itself. */
 window.nlfLoad=function(o){ adopt(o||{}); $('calcgo').click(); };
 window.nlfState=function(){return {recipe:recipe,calc:last,fmt:fmt,
   err:($('calcerr').hidden?'':$('calcerr').textContent),
   drawn:!!$('panelbox').querySelector('svg')};};

 /* ---------- paid-only wiring ------------------------------------------ */
 if(PAID){
  var raw=null; try{ raw=localStorage.getItem(KEY); }catch(e){}
  if(raw){
   var o=null; try{ o=JSON.parse(raw); }catch(e){}
   if(o&&!o.locked){ adopt(o); }
   try{ localStorage.removeItem(KEY); }catch(e){}
   note(o&&o.locked?
    'A locked recipe was found in this browser and has been cleared from storage. '+
    'Import your exported file to bring it in here.':
    'Your saved recipe was brought in from the free page and cleared from this '+
    "browser's storage. Save or export it again from here.");
  }
  var names={vertical:'nutrition-facts-vertical.svg',tabular:'nutrition-facts-tabular.svg',
             linear:'nutrition-facts-linear.svg'};
  ['vertical','tabular','linear'].forEach(function(f){
   $('dl-'+f).addEventListener('click',function(){
    if(!last||!last.ok){ alert('Run the calculator first.'); return; }
    var opts={draft:false};
    if(recipe.product||D.product) opts.caption=recipe.product||D.product;
    var svg=f==='vertical'?svgVertical(last,opts):
            f==='tabular'?svgTabular(last,opts):svgLinear(last,opts);
    download(names[f],'image/svg+xml',svg);
   });
  });
  $('dl-json').addEventListener('click',function(){
   var body=plain();
   body.product=recipe.product||D.product||'';
   body.confirmation={
    text:'I confirm this list is complete and in descending order of weight.',
    ticked:!!recipe.confirmed, at:new Date().toISOString()};
   body.sources={cfr_edition:D.edition,food_data:D.f.stamp,
     ecfr:'https://www.ecfr.gov/current/title-21/section-101.9',
     fdc:D.f.licence_url};
   download('nutrition-label-pack.json','application/json',JSON.stringify(body,null,1));
  });
  $('print').addEventListener('click',function(){
   if(!last||!last.ok){ alert('Run the calculator first.'); return; }
   draw(); window.print();
  });
 }
 note(PAID?'':'Nothing is saved until you press Save.');
})();
</script>
"""


def tool_html(paid: bool = False, product_name: str = "") -> str:
    """The whole tool: styles, data island, markup, script. One string."""
    blob = json.dumps(data_blob(paid, product_name), ensure_ascii=False,
                      separators=(",", ":"))
    blob = blob.replace("</", "<\\/")
    island = ('<script type="application/json" id="nlf-data">' + blob + "</script>")
    return css() + island + _skeleton(paid, product_name) + js()


if __name__ == "__main__":
    import sys
    paid = "--paid" in sys.argv
    out = tool_html(paid, "Example Granola" if paid else "")
    sys.stdout.write(out)
