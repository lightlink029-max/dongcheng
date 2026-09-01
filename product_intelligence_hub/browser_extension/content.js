function absoluteUrl(url){ try{return new URL(url,location.href).href;}catch{return url||'';} }
function number(text, pattern){const m=(text||'').match(pattern);return m?Number(m[1].replace(/,/g,'')):0;}
function productCard(link){
  let node=link;
  for(let i=0;i<8&&node?.parentElement;i++,node=node.parentElement){
    const txt=node.innerText||'';
    const count=node.querySelectorAll?.('a[href*="/product-detail/"]').length||0;
    if(txt.length>80&&txt.length<2200&&count>=1&&count<=5&&/(最低起订量|Min\. Order|已售|sold)/i.test(txt)) return node;
  }
  return link.closest('div')||link.parentElement;
}
function captureAlibaba(){
  const keyword=new URL(location.href).searchParams.get('SearchText')||document.querySelector('input[placeholder*="Search"]')?.value||'';
  const seen=new Set(), items=[];
  for(const titleLink of document.querySelectorAll('h2 a[href*="/product-detail/"]')){
    const url=absoluteUrl(titleLink.getAttribute('href'));
    const id=(url.match(/_(\d+)\.html/)||[])[1]||url;
    if(seen.has(id)) continue; seen.add(id);
    const card=productCard(titleLink), text=card?.innerText||'';
    const img=card?.querySelector('img[src],img[data-src]');
    const price=(text.match(/[¥$€£]\s*[\d,.]+(?:\s*-\s*[\d,.]+)?/)||[])[0]||'';
    const supplier=[...card.querySelectorAll('a')].find(a=>/company_profile\.html/.test(a.href));
    const rating=text.match(/(\d(?:\.\d)?)\/5\.0\s*\((\d+)\)/);
    const sold=number(text,/(?:已售|sold)\s*([\d,]+)/i);
    const repeat=number(text,/复购率\s*([\d.]+)%/);
    items.push({product_id:id,product_title:titleLink.textContent.trim(),product_url:url,main_image:absoluteUrl(img?.getAttribute('src')||img?.getAttribute('data-src')),supplier:supplier?.textContent.trim()||'',keywords:keyword,price_text:price,min_price:number(price,/([\d,.]+)/),moq:number(text,/(?:最低起订量[:：]?|Min\. Order[:：]?)\s*([\d,]+)/i),displayed_sales:sold,transactions:sold,repeat_purchase_rate:repeat,supplier_rating:rating?Number(rating[1]):0,review_count:rating?Number(rating[2]):0,heat_score:Math.min(100,Math.round(Math.log10(sold+1)*25+repeat*0.5)),source_page:location.href,captured_at:new Date().toISOString()});
  }
  return items;
}
chrome.runtime.onMessage.addListener((message,_sender,sendResponse)=>{
  if(message?.type==='PIH_CAPTURE') sendResponse({items:captureAlibaba()});
});
