const endpoint = document.querySelector('#endpoint');
const token = document.querySelector('#token');
const status = document.querySelector('#status');
const CAPTURE_MESSAGE = 'PIH_CAPTURE_V108';
const DETAIL_MESSAGE = 'PIH_DETAIL_V110';
chrome.storage.local.get(['endpoint','token','detailProgress'], v => {
  endpoint.value=v.endpoint||''; token.value=v.token||'';
  if(v.detailProgress?.message) status.textContent=v.detailProgress.message;
});
async function captureFromTab(tabId) {
  try {
    const current = await chrome.tabs.sendMessage(tabId,{type:CAPTURE_MESSAGE});
    if (current?.items) return current;
  } catch (error) {
    if (!String(error?.message||error).includes('Receiving end does not exist')) throw error;
  }
  await chrome.scripting.executeScript({target:{tabId},files:['content.js']});
  return await chrome.tabs.sendMessage(tabId,{type:CAPTURE_MESSAGE});
}
document.querySelector('#push').addEventListener('click', async () => {
  try {
    status.textContent='正在读取当前页面…';
    const ep=endpoint.value.trim(), tk=token.value.trim();
    if(!ep || !tk) throw new Error('请先填写接收地址和 Token');
    await chrome.storage.local.set({endpoint:ep,token:tk});
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!/^https:\/\/([a-z0-9-]+\.)*alibaba\.com\/trade\/search/i.test(tab.url||'')) throw new Error('请先打开 Alibaba 商品搜索结果页');
    const result=await captureFromTab(tab.id);
    if(!result?.items?.length) throw new Error('当前页面没有识别到商品，请确认位于 Alibaba 搜索结果页');
    status.textContent=`识别到 ${result.items.length} 件，正在推送…`;
    const response=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${tk}`},body:JSON.stringify({items:result.items})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok || !data.ok) throw new Error(data.error||`HTTP ${response.status}`);
    status.textContent=`完成：新增 ${data.created||0}，更新 ${data.updated||0}，跳过 ${data.skipped||0}`;
  } catch(e) { status.textContent=`失败：${e.message}`; }
});
function apiUrl(ep, action){
  const match=ep.match(/^(.*\/product-intelligence\/v1\/)ingest\/(\d+)\/?$/);
  if(!match) throw new Error('接收地址格式不正确');
  return `${match[1]}${action}/${match[2]}`;
}
async function waitTab(tabId){
  for(let i=0;i<40;i++){
    const tab=await chrome.tabs.get(tabId);
    if(tab.status==='complete') return;
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  throw new Error('详情页加载超时');
}
async function detailFromTab(tabId){
  try{return await chrome.tabs.sendMessage(tabId,{type:DETAIL_MESSAGE});}
  catch(error){
    if(!String(error?.message||error).includes('Receiving end does not exist')) throw error;
    await chrome.scripting.executeScript({target:{tabId},files:['content.js']});
    return await chrome.tabs.sendMessage(tabId,{type:DETAIL_MESSAGE});
  }
}
document.querySelector('#enrich').addEventListener('click',async()=>{
  try{
    const ep=endpoint.value.trim(),tk=token.value.trim();
    if(!ep||!tk) throw new Error('请先填写接收地址和 Token');
    await chrome.storage.local.set({endpoint:ep,token:tk});
    const started=await chrome.runtime.sendMessage({type:'PIH_START_DETAIL',endpoint:ep,token:tk});
    if(!started?.ok) throw new Error(started?.error||'无法启动后台任务');
    status.textContent='详情补充任务已在后台启动，切换标签页或关闭弹窗不会中断。';
  }catch(error){status.textContent=`详情补充停止：${error.message}`;}
});
