function absoluteUrl(url){ try{return new URL(url,location.href).href;}catch{return url||'';} }
function number(text, pattern){const m=(text||'').match(pattern);return m?Number(m[1].replace(/,/g,'')):0;}
function mainProductImage(card, productId){
  const matchedImages=[];
  for(const anchor of card?.querySelectorAll('a[href*="/product-detail/"]')||[]){
    const anchorId=(absoluteUrl(anchor.getAttribute('href')).match(/_(\d+)\.html/)||[])[1];
    if(anchorId!==productId) continue;
    for(const matched of anchor.querySelectorAll('img.searchx-product-e-slider__img[src*="s.alicdn.com/@sc"][src*="/kf/"]')){
      const src=absoluteUrl(matched.getAttribute('src'));
      if(src) matchedImages.push(src);
    }
  }
  matchedImages.sort((a,b)=>imageSizeScore(b)-imageSizeScore(a));
  if(matchedImages.length) return matchedImages[0];
  const primary=card?.querySelector('img.searchx-product-e-slider__img[src*="s.alicdn.com/@sc"][src*="/kf/"][src*="_300x300"]');
  if(primary?.getAttribute('src')) return absoluteUrl(primary.getAttribute('src'));
  const candidates=[];
  for(const img of card?.querySelectorAll('img')||[]){
    const srcset=(img.getAttribute('srcset')||'').split(',').map(x=>x.trim().split(/\s+/)[0]).filter(Boolean);
    const urls=[img.getAttribute('data-src'),img.getAttribute('data-lazy-src'),...srcset,img.getAttribute('src')].filter(Boolean);
    for(const raw of urls){
      const url=absoluteUrl(raw);
      if(!/alicdn\.com/i.test(url)||!/(?:\/|%2F)kf(?:\/|%2F)/i.test(url)) continue;
      if(/(?:logo|icon|flag|avatar|placeholder|loading)/i.test(url)) continue;
      let score=0;
      if(/s\.alicdn\.com\/@sc0[34]\/kf\//i.test(url)) score+=20;
      else if(/s\.alicdn\.com\/@sc\d+\/kf\//i.test(url)) score+=15;
      if(/_300x300\.(?:jpg|jpeg|png|webp)/i.test(url)) score+=10;
      if(/\.(?:jpg|jpeg|png|webp)(?:_|\?|$)/i.test(url)) score+=3;
      if((img.naturalWidth||0)>=150&&(img.naturalHeight||0)>=150) score+=5;
      candidates.push({url,score});
    }
  }
  candidates.sort((a,b)=>b.score-a.score);
  return candidates[0]?.url||'';
}
function imageSizeScore(url){
  if(/_300x300\./i.test(url)) return 100;
  if(/_100x100\./i.test(url)) return -100;
  const size=url.match(/_(\d+)x(\d+)\./);
  return size?Math.min(Number(size[1]),Number(size[2])):0;
}
function productCard(link){
  let node=link;
  let fallback=null;
  for(let i=0;i<8&&node?.parentElement;i++,node=node.parentElement){
    const txt=node.innerText||'';
    const count=node.querySelectorAll?.('a[href*="/product-detail/"]').length||0;
    if(txt.length>80&&txt.length<2200&&count>=1&&count<=5&&/(最低起订量|Min\. Order|已售|sold)/i.test(txt)){
      fallback ||= node;
      if(node.querySelector('img.searchx-product-e-slider__img')) return node;
    }
  }
  return fallback||link.closest('div')||link.parentElement;
}
function captureAlibaba(){
  const keyword=new URL(location.href).searchParams.get('SearchText')||document.querySelector('input[placeholder*="Search"]')?.value||'';
  const seen=new Set(), items=[];
  for(const titleLink of document.querySelectorAll('h2 a[href*="/product-detail/"]')){
    const url=absoluteUrl(titleLink.getAttribute('href'));
    const id=(url.match(/_(\d+)\.html/)||[])[1]||url;
    if(seen.has(id)) continue; seen.add(id);
    const card=productCard(titleLink), text=card?.innerText||'';
    const price=(text.match(/[¥$€£]\s*[\d,.]+(?:\s*-\s*[\d,.]+)?/)||[])[0]||'';
    const supplier=[...card.querySelectorAll('a')].find(a=>/company_profile\.html/.test(a.href));
    const rating=text.match(/(\d(?:\.\d)?)\/5\.0\s*\((\d+)\)/);
    const sold=number(text,/(?:已售|sold)\s*([\d,]+)/i);
    const repeat=number(text,/复购率\s*([\d.]+)%/);
    items.push({product_id:id,product_title:titleLink.textContent.trim(),product_url:url,main_image:mainProductImage(card,id),supplier:supplier?.textContent.trim()||'',keywords:keyword,price_text:price,min_price:number(price,/([\d,.]+)/),moq:number(text,/(?:最低起订量[:：]?|Min\. Order[:：]?)\s*([\d,]+)/i),displayed_sales:sold,transactions:sold,repeat_purchase_rate:repeat,supplier_rating:rating?Number(rating[1]):0,review_count:rating?Number(rating[2]):0,heat_score:Math.min(100,Math.round(Math.log10(sold+1)*25+repeat*0.5)),source_page:location.href,captured_at:new Date().toISOString()});
  }
  return items;
}
chrome.runtime.onMessage.addListener((message,_sender,sendResponse)=>{
  if(message?.type==='PIH_CAPTURE_V107') sendResponse({items:captureAlibaba()});
});
