const endpoint = document.querySelector('#endpoint');
const token = document.querySelector('#token');
const status = document.querySelector('#status');
chrome.storage.local.get(['endpoint','token'], v => { endpoint.value=v.endpoint||''; token.value=v.token||''; });
document.querySelector('#push').addEventListener('click', async () => {
  try {
    status.textContent='正在读取当前页面…';
    const ep=endpoint.value.trim(), tk=token.value.trim();
    if(!ep || !tk) throw new Error('请先填写接收地址和 Token');
    await chrome.storage.local.set({endpoint:ep,token:tk});
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const result=await chrome.tabs.sendMessage(tab.id,{type:'PIH_CAPTURE'});
    if(!result?.items?.length) throw new Error('当前页面没有识别到商品，请确认位于 Alibaba 搜索结果页');
    status.textContent=`识别到 ${result.items.length} 件，正在推送…`;
    const response=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${tk}`},body:JSON.stringify({items:result.items})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok || !data.ok) throw new Error(data.error||`HTTP ${response.status}`);
    status.textContent=`完成：新增 ${data.created||0}，更新 ${data.updated||0}，跳过 ${data.skipped||0}`;
  } catch(e) { status.textContent=`失败：${e.message}`; }
});
