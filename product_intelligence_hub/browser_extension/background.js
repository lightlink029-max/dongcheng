const DETAIL_MESSAGE = 'PIH_DETAIL_V110';

function apiUrl(endpoint, action) {
  const match = endpoint.match(/^(.*\/product-intelligence\/v1\/)ingest\/(\d+)\/?$/);
  if (!match) throw new Error('接收地址格式不正确');
  return `${match[1]}${action}/${match[2]}`;
}

async function setProgress(message, running = true) {
  await chrome.storage.local.set({detailProgress: {message, running, updatedAt: Date.now()}});
}

async function waitTab(tabId) {
  for (let i = 0; i < 60; i++) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === 'complete') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('详情页加载超时');
}

async function detailFromTab(tabId) {
  try {
    return await chrome.tabs.sendMessage(tabId, {type: DETAIL_MESSAGE});
  } catch (error) {
    if (!String(error?.message || error).includes('Receiving end does not exist')) throw error;
    await chrome.scripting.executeScript({target: {tabId}, files: ['content.js']});
    return await chrome.tabs.sendMessage(tabId, {type: DETAIL_MESSAGE});
  }
}

async function runDetailQueue(endpoint, token) {
  const headers = {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`};
  const queueResponse = await fetch(apiUrl(endpoint, 'detail-queue'), {headers});
  const queue = await queueResponse.json().catch(() => ({}));
  if (!queueResponse.ok || !queue.ok) throw new Error(queue.error || `HTTP ${queueResponse.status}`);
  if (!queue.items?.length) throw new Error('Odoo 中没有等待补充详情的产品');
  let done = 0, failed = 0;
  for (const item of queue.items) {
    await setProgress(`正在补充 ${done + failed + 1}/${queue.items.length}：${item.product_title}`);
    const tab = await chrome.tabs.create({url: item.product_url, active: true});
    try {
      await waitTab(tab.id);
      await new Promise(resolve => setTimeout(resolve, 1800));
      const detail = await detailFromTab(tab.id);
      detail.product_id = item.product_id;
      const response = await fetch(apiUrl(endpoint, 'detail-result'), {
        method: 'POST', headers, body: JSON.stringify(detail),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok || detail.error) {
        throw new Error(detail.error || result.error || `HTTP ${response.status}`);
      }
      done++;
    } catch (error) {
      failed++;
      await fetch(apiUrl(endpoint, 'detail-result'), {
        method: 'POST', headers,
        body: JSON.stringify({product_id: item.product_id, error: error.message}),
      }).catch(() => {});
      if (/验证码|登录|安全验证/.test(error.message)) throw error;
    } finally {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
    await new Promise(resolve => setTimeout(resolve, 1200));
  }
  await setProgress(`详情补充完成：成功 ${done}，失败 ${failed}`, false);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'PIH_START_DETAIL') return;
  chrome.storage.local.get('detailProgress').then(({detailProgress}) => {
    if (detailProgress?.running) {
      sendResponse({ok: false, error: '已有详情补充任务正在运行'});
      return;
    }
    setProgress('正在读取 Odoo 详情队列…').then(() => {
      runDetailQueue(message.endpoint, message.token).catch(async error => {
        await setProgress(`详情补充停止：${error.message}`, false);
      });
      sendResponse({ok: true});
    });
  });
  return true;
});
