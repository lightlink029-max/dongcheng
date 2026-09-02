const endpoint = document.querySelector('#endpoint');
const token = document.querySelector('#token');
const status = document.querySelector('#status');
const CAPTURE_MESSAGE = 'PIH_CAPTURE_V108';
const DETAIL_MESSAGE = 'PIH_DETAIL_V110';
chrome.storage.local.get(['endpoint','token'], v => { endpoint.value=v.endpoint||''; token.value=v.token||''; });
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
    const headers={'Content-Type':'application/json','Authorization':`Bearer ${tk}`};
    const queueResponse=await fetch(apiUrl(ep,'detail-queue'),{headers});
    const queue=await queueResponse.json();
    if(!queueResponse.ok||!queue.ok) throw new Error(queue.error||`HTTP ${queueResponse.status}`);
    if(!queue.items?.length) throw new Error('Odoo 中没有等待补充详情的产品');
    let done=0,failed=0;
    for(const item of queue.items){
      status.textContent=`正在补充 ${done+failed+1}/${queue.items.length}：${item.product_title}`;
      const tab=await chrome.tabs.create({url:item.product_url,active:true});
      try{
        await waitTab(tab.id);await new Promise(resolve=>setTimeout(resolve,1500));
        const detail=await detailFromTab(tab.id);detail.product_id=item.product_id;
        const result=await fetch(apiUrl(ep,'detail-result'),{method:'POST',headers,body:JSON.stringify(detail)});
        const resultData=await result.json().catch(()=>({}));
        if(!result.ok||!resultData.ok||detail.error) throw new Error(detail.error||resultData.error||`HTTP ${result.status}`);
        done++;
      }catch(error){
        failed++;
        await fetch(apiUrl(ep,'detail-result'),{method:'POST',headers,body:JSON.stringify({product_id:item.product_id,error:error.message})}).catch(()=>{});
        if(/验证码|登录|安全验证/.test(error.message)) throw error;
      }finally{await chrome.tabs.remove(tab.id).catch(()=>{});}
      await new Promise(resolve=>setTimeout(resolve,1200));
    }
    status.textContent=`详情补充完成：成功 ${done}，失败 ${failed}`;
  }catch(error){status.textContent=`详情补充停止：${error.message}`;}
});
