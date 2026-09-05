const DETAIL_MESSAGE = 'PIH_DETAIL_V110';
const YIWUGO_CONTACT_MESSAGE = 'PIH_YIWUGO_SUPPLIER_CONTACT_V100';

async function enrichYiwugoContacts(items) {
  const cache = new Map();
  const urls = [...new Set((items || []).map(item => item.supplier_url).filter(Boolean))];
  for (let index = 0; index < urls.length; index++) {
    const url = urls[index];
    await setProgress(`正在读取义乌购商家联系方式 ${index + 1}/${urls.length}`);
    const tab = await chrome.tabs.create({url, active: false});
    try {
      await waitTab(tab.id);
      await new Promise(resolve => setTimeout(resolve, 2200 + Math.floor(Math.random() * 1800)));
      const guard = await chrome.scripting.executeScript({
        target: {tabId: tab.id},
        func: () => /验证码|安全验证|滑块验证|访问过于频繁|请登录后继续/.test(document.body?.innerText || ''),
      });
      if (guard?.[0]?.result) throw new Error('义乌购触发安全验证，已停止补充商家联系方式');
      let contact;
      try { contact = await chrome.tabs.sendMessage(tab.id, {type: YIWUGO_CONTACT_MESSAGE}); }
      catch (_) {
        await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['content.js']});
        contact = await chrome.tabs.sendMessage(tab.id, {type: YIWUGO_CONTACT_MESSAGE});
      }
      cache.set(url, contact || {});
    } catch (error) {
      cache.set(url, {});
      if (/安全验证|验证码|访问过于频繁/.test(error.message || '')) throw error;
    }
    finally { await chrome.tabs.remove(tab.id).catch(() => {}); }
    // Randomized 4-7 second interval avoids opening supplier pages in a fixed,
    // machine-like rhythm. Duplicate supplier URLs are already visited once.
    await new Promise(resolve => setTimeout(resolve, 4000 + Math.floor(Math.random() * 3000)));
  }
  await setProgress(`商家联系方式补充完成：${urls.length} 家`, false);
  return (items || []).map(item => ({...item, ...(cache.get(item.supplier_url) || {})}));
}

async function runSupplierContactQueue(endpoint, token) {
  const headers = {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`};
  const response = await fetch(apiUrl(endpoint, 'supplier-contact-queue'), {headers});
  const queue = await response.json().catch(() => ({}));
  if (!response.ok || !queue.ok) throw new Error(queue.error || `HTTP ${response.status}`);
  if (!queue.items?.length) throw new Error('没有已选择且等待补充的义乌购商家');
  for (let index = 0; index < queue.items.length; index++) {
    const item = queue.items[index];
    await setProgress(`正在补充商家 ${index + 1}/${queue.items.length}：${item.supplier_name || ''}`);
    const enriched = await enrichYiwugoContacts([{supplier_url: item.supplier_url}]);
    const contact = enriched[0] || {};
    const saved = await fetch(apiUrl(endpoint, 'supplier-contact-result'), {
      method: 'POST', headers, body: JSON.stringify({...contact, offer_id: item.offer_id}),
    });
    const result = await saved.json().catch(() => ({}));
    if (!saved.ok || !result.ok) throw new Error(result.error || `HTTP ${saved.status}`);
  }
  await setProgress(`本批商家信息补充完成：${queue.items.length} 家`, false);
}

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
  if (message?.type === 'PIH_DOUYIN_SYNC') {
    try {
      const match = (message.endpoint || '').match(/^(.*\/product-intelligence\/v1\/)ingest\/(\d+)\/?$/);
      if (!match) throw new Error('接收地址格式不正确');
      const url = `${match[1]}douyin-selection/${match[2]}/${Number(message.contentId || 0)}`;
      fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${message.token || ''}`},
        body: JSON.stringify({urls: Array.isArray(message.urls) ? message.urls : []}),
      }).then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
        sendResponse(data);
      }).catch(error => sendResponse({ok: false, error: error.message}));
    } catch (error) {
      sendResponse({ok: false, error: error.message});
    }
    return true;
  }
  if (message?.type === 'PIH_ENRICH_YIWUGO_CONTACTS') {
    enrichYiwugoContacts(message.items).then(items => sendResponse({ok: true, items}))
      .catch(error => sendResponse({ok: false, error: error.message, items: message.items || []}));
    return true;
  }
  if (message?.type === 'PIH_START_SUPPLIER_CONTACTS') {
    setProgress('正在读取商家信息补充队列…').then(() => {
      runSupplierContactQueue(message.endpoint, message.token).catch(async error => {
        await setProgress(`商家信息补充停止：${error.message}`, false);
      });
      sendResponse({ok: true});
    });
    return true;
  }
  if (message?.type === 'PIH_SOURCING_MAIN_WORLD_UPLOAD' || message?.type === 'PIH_1688_MAIN_WORLD_UPLOAD') {
    const tabId = _sender.tab?.id;
    if (!tabId) {
      sendResponse({ok: false, error: '无法识别当前货源搜索标签页'});
      return;
    }
    chrome.scripting.executeScript({
      target: {tabId}, world: 'MAIN',
      args: [message.data, message.mimeType || 'image/jpeg', message.platform || '1688'],
      func: async (base64, mimeType, platform) => {
        let input = null;
        for (let i = 0; i < 20 && !input; i++) {
          input = document.querySelector('input[type="file"][accept*="image"],input[type="file"]');
          if (!input) await new Promise(resolve => setTimeout(resolve, 150));
        }
        if (!input) return {ok: false, error: '未找到图片上传控件'};
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const file = new File([bytes], 'pih-reference.jpg', {type: mimeType});
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
        input.dispatchEvent(new Event('change', {bubbles: true, composed: true}));
        if (platform === 'yiwugo' || platform === 'douyin') {
          // YiwuGo's upload component starts image retrieval from the file
          // input change event. Its top orange button is only for URL input.
          await new Promise(resolve => setTimeout(resolve, 1800));
          return {ok: true, searched: true};
        }
        for (let i = 0; i < 80; i++) {
          const searchButton = [...document.querySelectorAll('button,[role="button"],a,div,span')]
            .filter(node => (node.textContent || '').replace(/\s+/g, '').trim() === '搜索图片')
            .filter(node => node.getClientRects().length > 0)
            .sort((left, right) => left.children.length - right.children.length)[0];
          const enabled = searchButton && !searchButton.disabled
            && searchButton.getAttribute('aria-disabled') !== 'true'
            && searchButton.getClientRects().length > 0;
          if (enabled) {
            searchButton.scrollIntoView({block: 'center', inline: 'center'});
            searchButton.click();
            return {ok: true, searched: true};
          }
          await new Promise(resolve => setTimeout(resolve, 250));
        }
        return {ok: true, searched: false};
      },
    }).then(results => sendResponse(results?.[0]?.result || {ok: false, error: '1688页面未返回上传结果'}))
      .catch(error => sendResponse({ok: false, error: error.message}));
    return true;
  }
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
