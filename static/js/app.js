
const $ = (selector) => document.querySelector(selector);
let registerMode = false;
let selectedFile = null;
let noticeTimer;
const classInfo = {};
function tell(message){const notice=$('#notice');notice.textContent=message;notice.classList.add('show');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>notice.classList.remove('show'),3000)}
async function api(url,options={}){const response=await fetch(url,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});const data=await response.json();if(!response.ok)throw new Error(data.error||'Something went wrong.');return data}
function showAuth(mode){registerMode=mode;$('#authHeading').textContent=mode?'Create your journal':'Welcome back';$('#authCopy').textContent=mode?'Save image checks in your own private field journal.':'Sign in to review your grove and image analyses.';$('#authSubmit').innerHTML=mode?'Create account <span aria-hidden="true">→</span>':'Sign in <span aria-hidden="true">→</span>';$('#authSwitchText').textContent=mode?'Already have an account?':'New to the journal?';$('#authSwitch').textContent=mode?'Sign in':'Create account';$('#password').autocomplete=mode?'new-password':'current-password';$('#authError').textContent=''}
$('#authSwitch').addEventListener('click',()=>showAuth(!registerMode));
$('#authForm').addEventListener('submit',async event=>{event.preventDefault();$('#authError').textContent='';const payload={email:$('#email').value,password:$('#password').value};try{await api(registerMode?'/api/register':'/api/login',{method:'POST',body:JSON.stringify(payload)});enterApp(payload.email)}catch(error){$('#authError').textContent=error.message}});
function enterApp(email){$('#loginShell').style.display='none';$('#appShell').style.display='block';const first=email.split('@')[0];$('#profileName').textContent=first;$('#avatar').textContent=(first[0]||'B').toUpperCase();showView('overview');loadAll()}
$('#logoutBtn').addEventListener('click',async()=>{await api('/api/logout',{method:'POST'});$('#appShell').style.display='none';$('#loginShell').style.display='grid';$('#password').value='';tell('Signed out of your field journal.')});
function showView(name){document.querySelectorAll('.view').forEach(view=>view.classList.toggle('active',view.id==='view-'+name));document.querySelectorAll('.nav button').forEach(button=>button.classList.toggle('active',button.dataset.view===name));$('#breadcrumb').textContent='FIELD JOURNAL / '+name.toUpperCase().replace('DIAGNOSE','IMAGE TEST').replace('HISTORY','MY STORAGE').replace('DATASET','IMAGE LIBRARY');if(name==='history')loadHistory();if(name==='analytics')loadAnalytics()}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.go)));
function tagClass(type){return type==='Disease'?'disease':type==='Not a leaf'?'neutral':''}
function classRow(item){return `<div class="class-row"><img class="tiny-image" src="${item.image_url}" alt=""><div><div class="class-name">${item.title}</div><div class="class-kind">${item.type}</div></div><span class="class-count">${Number(item.count).toLocaleString()}</span></div>`}
function renderClasses(data){data.classes.forEach(item=>classInfo[item.name]=item);$('#overviewClasses').innerHTML=data.classes.map(classRow).join('');$('#datasetGrid').innerHTML=data.classes.map(item=>`<article class="dataset-card"><img src="${item.image_url}" alt="Example image: ${item.title}" loading="lazy"><div class="dataset-copy"><span class="class-kind">${item.type}</span><h3>${item.title}</h3><p>${item.description}</p><strong>${Number(item.count).toLocaleString()} ORIGINAL IMAGES</strong></div></article>`).join('');$('#datasetTotal').textContent=Number(data.total).toLocaleString()+' ORIGINAL IMAGES';$('#metricImages').textContent=Number(data.total).toLocaleString();$('#metricClasses').textContent=data.classes.length}
function renderHistory(items){const markup=items.length?items.slice(0,5).map(item=>`<div class="class-row"><img class="tiny-image" src="${item.image_url}" alt=""><div><div class="class-name">${item.title}</div><div class="class-kind">${escapeHtml(item.name)} · ${formatDate(item.created_at)}</div></div><span class="tag ${tagClass(item.type)}">${item.type}</span></div>`).join(''):'<div class="empty">No images yet. Your first field check will appear here.</div>';$('#overviewHistory').innerHTML=markup;
  $('#historyList').innerHTML=items.length?items.map(item=>`<article class="history-item"><img src="${item.image_url}" alt=""><div><div class="history-name">${escapeHtml(item.name)}</div><div class="history-meta">${item.title} · ${formatDate(item.created_at)}</div></div><span class="tag ${tagClass(item.type)}">${item.type}</span><button class="delete-btn" data-delete="${item.id}" aria-label="Delete ${escapeHtml(item.name)}">Delete</button></article>`).join(''):'<div class="empty">No saved images yet. Upload a photo to begin your field journal.</div>';
  document.querySelectorAll('[data-delete]').forEach(button=>button.addEventListener('click',async()=>{try{await api('/api/history/'+button.dataset.delete,{method:'DELETE'});tell('Image removed from your storage.');loadAll()}catch(error){tell(error.message)}}))}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function formatDate(value){return new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}
async function loadHistory(){try{const data=await api('/api/history');renderHistory(data.history)}catch(error){if(error.message!=='Please sign in to continue.')tell(error.message)}}
async function loadAll(){try{const [dashboard,classes,history]=await Promise.all([api('/api/dashboard'),api('/api/classes'),api('/api/history')]);renderClasses(classes);renderHistory(history.history);$('#metricScans').textContent=dashboard.scans;$('#metricFlagged').textContent=dashboard.flagged;$('#modelStatus').textContent=dashboard.classifier_ready?'Model ready':'Model needs training';$('#modelDetail').textContent=dashboard.classifier_ready?`Validation accuracy ${dashboard.validation_accuracy.toFixed(1)}% · cutoff ${dashboard.confidence_threshold.toFixed(1)}%`:'Run python train.py to build the local classifier.'}catch(error){tell(error.message)}}
const chartColors=['#477a4c','#d27659','#d8ac50','#6686a0'];
function formatPercent(value){return Number.isFinite(Number(value))?Number(value).toFixed(1)+'%':'—'}
function renderValidationBars(metrics){const rows=[['Accuracy','accuracy_pct'],['Precision','precision_pct'],['Recall / sensitivity','recall_pct'],['Specificity','specificity_pct'],['F1 score','f1_pct']];$('#validationBars').innerHTML=rows.map(([label,key])=>{const value=Number(metrics[key])||0;return `<div class="validation-bar-row"><span class="validation-bar-label">${label}</span><div class="validation-bar-track"><div class="validation-bar-fill" style="width:${Math.max(0,Math.min(100,value))}%"></div></div><span class="validation-bar-value">${formatPercent(value)}</span></div>`}).join('');$('#validationFootnote').textContent=`Macro averages from ${metrics.validation_samples||0} held-out images; ${metrics.training_samples||0} images used to fit this model. R² is not defined for class prediction.`}
function renderConfusionMatrix(metrics){const classes=metrics.classes||[];const matrix=metrics.confusion_matrix||[];const perClass=metrics.per_class||[];const labels=classes.map(name=>classInfo[name]?.title||name);const header=labels.map(label=>`<th scope="col">${label}</th>`).join('');const rows=classes.map((name,rowIndex)=>{const values=matrix[rowIndex]||[];const total=values.reduce((sum,value)=>sum+Number(value),0);const cells=classes.map((_,columnIndex)=>{const value=Number(values[columnIndex])||0;const ratio=total?value/total:0;const shade=(0.05+ratio*.58).toFixed(2);return `<td style="background:rgba(71,122,76,${shade})" title="${labels[rowIndex]} predicted as ${labels[columnIndex]}">${value}</td>`}).join('');return `<tr><th scope="row" class="row-label">${labels[rowIndex]}</th>${cells}<td class="matrix-support">${perClass[rowIndex]?.support??total}</td></tr>`}).join('');$('#confusionMatrix').innerHTML=`<table class="confusion-table"><thead><tr><th class="axis-label" scope="col">Actual / predicted</th>${header}<th scope="col">N</th></tr></thead><tbody>${rows}</tbody></table>`}
function drawPredictionPie(distribution){const canvas=$('#historyPieChart');const bounds=canvas.getBoundingClientRect();const size=Math.max(120,Math.min(bounds.width||200,bounds.height||200));const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.round(size*ratio);canvas.height=Math.round(size*ratio);const context=canvas.getContext('2d');context.setTransform(ratio,0,0,ratio,0,0);const center=size/2;const radius=size*.43;const total=distribution.reduce((sum,item)=>sum+Number(item.count||0),0);let angle=-Math.PI/2;if(!total){context.beginPath();context.arc(center,center,radius,0,Math.PI*2);context.fillStyle='#e5e8de';context.fill();return}distribution.forEach((item,index)=>{const portion=Number(item.count||0)/total;if(!portion)return;const next=angle+portion*Math.PI*2;context.beginPath();context.moveTo(center,center);context.arc(center,center,radius,angle,next);context.closePath();context.fillStyle=chartColors[index%chartColors.length];context.fill();context.strokeStyle='#fffdf7';context.lineWidth=2;context.stroke();angle=next})}
function renderPredictionMix(distribution){const total=distribution.reduce((sum,item)=>sum+Number(item.count||0),0);$('#predictionTotal').textContent=total.toLocaleString()+' SAVED';$('#historyPieEmpty').style.display=total?'none':'block';$('#historyPieLegend').innerHTML=distribution.map((item,index)=>{const count=Number(item.count||0);const share=total?Math.round(count/total*100):0;return `<div class="pie-legend-row"><span class="pie-legend-swatch" style="background:${chartColors[index%chartColors.length]}"></span><span class="pie-legend-name">${item.title}</span><span class="pie-legend-value">${count} · ${share}%</span></div>`}).join('');drawPredictionPie(distribution)}
function renderHistoryTrend(history){const days=history.daily_scans||[];const peak=Math.max(1,...days.map(day=>Number(day.count)||0));$('#historyTotal').textContent=Number(history.total||0).toLocaleString()+' SCANS';$('#historyTrend').innerHTML=days.map(day=>{const count=Number(day.count)||0;const height=count?Math.max(7,count/peak*112):2;const date=new Date(day.date+'T12:00:00');const label=date.toLocaleDateString(undefined,{month:'numeric',day:'numeric'});return `<div class="trend-column" title="${date.toLocaleDateString()}: ${count} saved scans"><span class="trend-count">${count||''}</span><div class="trend-bar-track"><div class="trend-bar" style="height:${height}px"></div></div><span class="trend-date">${label}</span></div>`}).join('')}
function renderAnalytics(data){const metrics=data.validation_metrics||{};$('#analyticsAccuracy').textContent=formatPercent(metrics.accuracy_pct);$('#analyticsPrecision').textContent=formatPercent(metrics.precision_pct);$('#analyticsRecall').textContent=formatPercent(metrics.recall_pct);$('#analyticsSpecificity').textContent=formatPercent(metrics.specificity_pct);$('#analyticsF1').textContent=formatPercent(metrics.f1_pct);$('#validationSampleCount').textContent=`${metrics.validation_samples||0} VALIDATION IMAGES`;renderValidationBars(metrics);renderConfusionMatrix(metrics);renderPredictionMix(data.prediction_distribution||[]);renderHistoryTrend(data.history||{daily_scans:[],total:0})}
async function loadAnalytics(){try{renderAnalytics(await api('/api/analytics'))}catch(error){tell(error.message)}}
$('#imageInput').addEventListener('change',event=>setImage(event.target.files[0]));
function setImage(file){if(!file)return;if(file.size>12*1024*1024){tell('Image must be smaller than 12 MB.');return}selectedFile=file;$('#previewImage').src=URL.createObjectURL(file);$('#previewImage').style.display='block';$('#uploadSymbol').style.display='none';$('#uploadPrompt').textContent='Image ready to analyze';$('#uploadHint').textContent='Choose another photo to replace it';$('#uploadFilename').textContent=file.name+' · '+(file.size/1024/1024).toFixed(2)+' MB';$('#analyzeBtn').disabled=false;$('#resultPanel').style.display='none'}
$('#dropZone').addEventListener('dragover',event=>{event.preventDefault();$('#dropZone').classList.add('dragover')});$('#dropZone').addEventListener('dragleave',()=>$('#dropZone').classList.remove('dragover'));$('#dropZone').addEventListener('drop',event=>{event.preventDefault();$('#dropZone').classList.remove('dragover');setImage(event.dataTransfer.files[0])});
$('#analyzeBtn').addEventListener('click',async()=>{if(!selectedFile)return;const button=$('#analyzeBtn');button.disabled=true;button.textContent='Comparing with the image library…';const form=new FormData();form.append('image',selectedFile);try{const result=await api('/api/predict',{method:'POST',body:form});$('#resultPanel').style.display='block';$('#resultImage').src=result.image_url;$('#resultTitle').textContent=result.title;$('#resultTag').textContent=result.type;$('#resultTag').className='tag '+tagClass(result.type);$('#signalValue').textContent=result.score+'%';$('#signalFill').style.width=result.score+'%';$('#resultDescription').textContent=result.description;$('#resultNote').textContent=result.note;$('#resultDate').textContent=formatDate(result.created_at);$('#resultPanel').scrollIntoView({behavior:'smooth',block:'nearest'});tell('Analysis complete. Image saved to your storage.');loadAll()}catch(error){tell(error.message)}finally{button.disabled=false;button.innerHTML='Analyze image <span aria-hidden="true">→</span>'}});
function updateClock(){const now=new Date();$('#clock').textContent=now.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});$('#todayStamp').textContent=now.toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'}).toUpperCase()}
updateClock();setInterval(updateClock,30000);
api('/api/session').then(data=>{if(data.authenticated)enterApp(data.email)}).catch(()=>{});
const canvas=$('#particles');
const ctx=canvas.getContext('2d');
const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const pointer={x:-1000,y:-1000,active:false,pulseAt:0};
let motes=[];
function resizeCanvas(){
  const ratio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=window.innerWidth*ratio;
  canvas.height=window.innerHeight*ratio;
  ctx.setTransform(ratio,0,0,ratio,0,0);
  const count=Math.min(56,Math.max(24,Math.round(window.innerWidth/24)));
  motes=Array.from({length:count},(_,index)=>({x:Math.random()*innerWidth,y:Math.random()*innerHeight,r:1+Math.random()*1.7,vx:-.16+Math.random()*.32,vy:-.16+Math.random()*.32,phase:Math.random()*Math.PI*2,hue:index%5===0?28:105}));
  drawNetwork(performance.now());
}
function drawNetwork(time){
  const width=window.innerWidth;
  const height=window.innerHeight;
  ctx.clearRect(0,0,width,height);
  for(let index=0;index<motes.length;index++){
    const mote=motes[index];
    if(!reducedMotion){
      mote.x+=mote.vx;
      mote.y+=mote.vy;
      mote.x+=Math.sin(time*.00035+mote.phase)*.12;
      mote.y+=Math.cos(time*.0003+mote.phase)*.1;
      if(pointer.active){
        const dx=mote.x-pointer.x;
        const dy=mote.y-pointer.y;
        const distance=Math.hypot(dx,dy)||1;
        if(distance<145){const force=(145-distance)/145*.012;mote.x+=dx/distance*force*18;mote.y+=dy/distance*force*18}
      }
      if(mote.x<-8)mote.x=width+8;
      if(mote.x>width+8)mote.x=-8;
      if(mote.y<-8)mote.y=height+8;
      if(mote.y>height+8)mote.y=-8;
    }
    for(let otherIndex=index+1;otherIndex<motes.length;otherIndex++){
      const other=motes[otherIndex];
      const dx=other.x-mote.x;
      const dy=other.y-mote.y;
      const distance=Math.hypot(dx,dy);
      if(distance>132)continue;
      const pointerDistance=pointer.active?Math.hypot((mote.x+other.x)/2-pointer.x,(mote.y+other.y)/2-pointer.y):999;
      const boost=pointerDistance<180?.13*(1-pointerDistance/180):0;
      ctx.beginPath();
      ctx.moveTo(mote.x,mote.y);
      ctx.lineTo(other.x,other.y);
      ctx.strokeStyle=`rgba(73,111,70,${.025+(1-distance/132)*.105+boost})`;
      ctx.lineWidth=1;
      ctx.stroke();
    }
    const pointerDistance=pointer.active?Math.hypot(mote.x-pointer.x,mote.y-pointer.y):999;
    const glow=pointerDistance<125?(1-pointerDistance/125)*.38:0;
    ctx.beginPath();
    ctx.fillStyle=`hsla(${mote.hue},35%,38%,${.16+glow})`;
    ctx.arc(mote.x,mote.y,mote.r+glow*3,0,Math.PI*2);
    ctx.fill();
  }
  if(pointer.pulseAt){
    const age=time-pointer.pulseAt;
    if(age<900){
      const radius=age*.13;
      ctx.beginPath();
      ctx.arc(pointer.x,pointer.y,radius,0,Math.PI*2);
      ctx.strokeStyle=`rgba(210,118,89,${.28*(1-age/900)})`;
      ctx.lineWidth=1.5;
      ctx.stroke();
    }else pointer.pulseAt=0;
  }
  if(!reducedMotion)requestAnimationFrame(drawNetwork);
}
window.addEventListener('pointermove',event=>{pointer.x=event.clientX;pointer.y=event.clientY;pointer.active=true},{passive:true});
window.addEventListener('pointerleave',()=>{pointer.active=false});
window.addEventListener('pointerdown',event=>{pointer.x=event.clientX;pointer.y=event.clientY;pointer.active=true;pointer.pulseAt=performance.now()});
window.addEventListener('resize',resizeCanvas);
resizeCanvas();
if(!reducedMotion)requestAnimationFrame(drawNetwork);
