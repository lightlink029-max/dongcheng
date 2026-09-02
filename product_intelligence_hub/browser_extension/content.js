function absoluteUrl(url){ try{return new URL(url,location.href).href;}catch{return url||'';} }
function number(text, pattern){const m=(text||'').match(pattern);return m?Number(m[1].replace(/,/g,'')):0;}
function mainProductImage(card, productId){
  const primaryImages=[...(card?.querySelectorAll('img.searchx-product-e-slider__img[src*="s.alicdn.com/@sc"][src*="/kf/"]')||[])];
  const primary300=primaryImages.find(img=>/_300x300\.(?:jpg|jpeg|png|webp)/i.test(img.currentSrc||img.getAttribute('src')||''));
  if(primary300) return absoluteUrl(primary300.currentSrc||primary300.getAttribute('src'));
  if(primaryImages.length===1) return absoluteUrl(primaryImages[0].currentSrc||primaryImages[0].getAttribute('src'));
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
  for(let i=0;i<10&&node?.parentElement;i++,node=node.parentElement){
    const primaryCount=node.querySelectorAll?.('img.searchx-product-e-slider__img').length||0;
    if(primaryCount===1) return node;
    if(!fallback&&primaryCount>0) fallback=node;
    const txt=node.innerText||'';
    const count=node.querySelectorAll?.('a[href*="/product-detail/"]').length||0;
    if(txt.length>80&&txt.length<2200&&count>=1&&count<=5&&/(最低起订量|Min\. Order|已售|sold)/i.test(txt)){
      fallback ||= node;
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
function cleanDetailLines(text){
  return (text||'').split('\n').map(line=>line.replace(/\s+/g,' ').trim()).filter(line=>line&&line.length<800);
}
function sectionLines(lines,startPattern,endPattern){
  const start=lines.findIndex(line=>startPattern.test(line));
  if(start<0) return [];
  let end=lines.slice(start+1).findIndex(line=>endPattern.test(line));
  end=end<0?Math.min(lines.length,start+120):start+1+end;
  return lines.slice(start+1,end).filter(line=>
    !/^(下载扩展程序|聊天|立即联系|联系我们|查看详情|Learn more)$/i.test(line)
  );
}
function labelledDetails(lines,labelPattern){
  const result=[];
  for(let i=0;i<lines.length;i++){
    if(!labelPattern.test(lines[i])) continue;
    result.push(lines[i]);
    if(lines[i+1]&&!labelPattern.test(lines[i+1])) result.push(lines[i+1]);
  }
  return [...new Set(result)].join('\n').slice(0,10000);
}
function breadcrumbCategory(){
  for(const script of document.querySelectorAll('script[type="application/ld+json"]')){
    try{
      const data=JSON.parse(script.textContent||'{}');
      const objects=Array.isArray(data)?data:[data];
      const breadcrumb=objects.find(item=>item?.['@type']==='BreadcrumbList');
      const names=(breadcrumb?.itemListElement||[]).map(item=>item?.item?.name||item?.name).filter(Boolean);
      if(names.length) return names.slice(-3).join(' > ');
    }catch(_error){}
  }
  return [...document.querySelectorAll('[class*="breadcrumb"] a')]
    .map(a=>(a.textContent||'').replace(/\s+/g,' ').trim())
    .filter(text=>text&&text.length<100&&!/Alibaba Lens|比价|扩展程序/i.test(text))
    .slice(-3).join(' > ');
}
function captureAlibabaDetail(){
  const text=(document.body?.innerText||'').slice(0,200000);
  if(/captcha|验证码|verify you are human|security verification/i.test(text)) return {error:'页面要求登录或安全验证，请人工处理后重试。'};
  const productId=(location.href.match(/_(\d+)\.html/)||[])[1]||'';
  const lines=cleanDetailLines(text);
  const attributes=sectionLines(
    lines,/^(重要属性|Key attributes|产品属性|Product attributes|Specifications)$/i,
    /^(包装和交付|包装与交付|Packaging and delivery|产品描述|Product Description|供应商介绍|Supplier introduction)$/i
  );
  const delivery=sectionLines(
    lines,/^(包装和交付|包装与交付|Packaging and delivery)$/i,
    /^(产品描述|Product Description|供应商介绍|Supplier introduction|评论|Reviews)$/i
  );
  const packagingLabels=/^(包装详情|包装细节|包装类型|销售单位|单件包装尺寸|单件毛重|Packaging Details|Package Type|Selling Units|Single package size|Single gross weight)/i;
  const shippingLabels=/^(港口|供应能力|交货期|发货|运输|Port|Supply Ability|Lead time|Delivery|Shipping)/i;
  return {
    product_id:productId,
    category:breadcrumbCategory(),
    important_attributes:attributes.join('\n').slice(0,10000),
    packaging_information:labelledDetails(delivery,packagingLabels),
    shipping_information:labelledDetails(delivery,shippingLabels),
  };
}
chrome.runtime.onMessage.addListener((message,_sender,sendResponse)=>{
  if(message?.type==='PIH_CAPTURE_V108') sendResponse({items:captureAlibaba()});
  if(message?.type==='PIH_DETAIL_V110') sendResponse(captureAlibabaDetail());
});
