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
function normalizedText(node){
  return (node?.getAttribute?.('title')||node?.textContent||'').replace(/\s+/g,' ').trim();
}
function uniquePairs(pairs){
  const seen=new Set();
  return pairs.filter(([name,value])=>{
    const key=`${name}\u0000${value}`;
    if(!name||!value||seen.has(key)) return false;
    seen.add(key); return true;
  });
}
function formatPairs(pairs){
  return uniquePairs(pairs).map(([name,value])=>`${name}：${value}`).join('\n').slice(0,10000);
}
function attributeRows(root){
  if(!root) return [];
  return [...root.querySelectorAll('[data-testid="module-attribute-row"]')].map(row=>[
    normalizedText(row.querySelector('[data-testid="module-attribute-name"]')),
    normalizedText(row.querySelector('[data-testid="module-attribute-value"]')),
  ]);
}
function coreIndustryRows(){
  const root=document.querySelector('[data-testid="three-column-key-attributes"]');
  if(!root) return [];
  const pairs=[];
  for(const row of root.querySelectorAll('[data-testid="three-column-key-attributes-row"]')){
    for(const cell of row.children){
      const values=[...cell.querySelectorAll(':scope > p')].map(normalizedText).filter(Boolean);
      if(values.length>=2) pairs.push([values[0],values[1]]);
    }
  }
  return pairs;
}
function attributeGroup(titlePattern){
  return [...document.querySelectorAll('[data-testid="module-attribute-group"]')]
    .find(group=>titlePattern.test(normalizedText(group.querySelector('[data-testid="module-attribute-group-title"]'))));
}
function importantRows(){
  const root=document.querySelector('[data-testid="module-attribute"]');
  if(!root) return [];
  const pairs=[];
  for(const group of root.querySelectorAll('[data-testid="module-attribute-group"]')){
    const title=normalizedText(group.querySelector('[data-testid="module-attribute-group-title"]'));
    if(/包装和发货信息|Packaging and shipping information|Packaging and delivery/i.test(title)) continue;
    pairs.push(...attributeRows(group));
  }
  return pairs;
}
function shippingRows(){
  const result=[];
  for(const heading of document.querySelectorAll('h2,h3,h4')){
    if(!/^(交货时间|Lead time|Delivery time)$/i.test(normalizedText(heading))) continue;
    const container=heading.parentElement;
    for(const row of container?.querySelectorAll('table tr')||[]){
      const cells=[...row.querySelectorAll('th,td')].map(normalizedText).filter(Boolean);
      if(cells.length) result.push(cells.join(' | '));
    }
  }
  return [...new Set(result)].join('\n').slice(0,10000);
}
function originalAlibabaImageUrl(raw){
  const url=absoluteUrl(raw||'');
  if(!url) return '';
  return url
    .replace(/\.(jpg|jpeg|png|webp)_\d+x\d+(?:q\d+)?\.\1(?=\?|$)/i,'.$1')
    .replace(/[?&](?:webp|avif)=close/gi,'')
    .replace(/[?&]$/,'');
}
function detailPhotos(){
  const mainImage=document.querySelector('[data-testid="product-image-view"]');
  if(!mainImage) return [];
  const result=[], seen=new Set();
  for(const img of mainImage.querySelectorAll('[data-testid="main-image-media-frame"] img, [data-testid="media-image"] img')){
    const rawUrls=[
      img.currentSrc,img.getAttribute('src'),img.getAttribute('data-src'),img.getAttribute('data-lazy-src'),
      ...(img.getAttribute('srcset')||'').split(',').map(part=>part.trim().split(/\s+/)[0]),
    ].filter(Boolean);
    for(const raw of rawUrls){
      const url=originalAlibabaImageUrl(raw);
      if(!/^https?:\/\//i.test(url)||!/(?:alicdn\.com|alibaba\.com)/i.test(url)) continue;
      if(!/(?:\/|%2F)kf(?:\/|%2F)/i.test(url)) continue;
      if(/(?:logo|icon|avatar|flag|loading|placeholder)/i.test(url)) continue;
      const asset=(url.match(/\/kf\/([^/?]+)/i)||[])[1]||url;
      if(seen.has(asset)) continue;
      seen.add(asset);
      result.push({url,name:img.getAttribute('alt')||''});
      break;
    }
  }
  return result.slice(0,30);
}
function detailVideos(){
  const mainImage=document.querySelector('[data-testid="product-image-view"]');
  if(!mainImage) return [];
  const urls=[];
  for(const node of mainImage.querySelectorAll('video,video source')){
    urls.push(node.currentSrc,node.getAttribute('src'),node.getAttribute('data-src'));
  }
  return [...new Set(urls
    .filter(raw=>raw&& !/^(?:null|undefined|about:blank)$/i.test(String(raw).trim()))
    .map(absoluteUrl)
    .filter(url=>/^https?:\/\//i.test(url)&& !/\/(?:null|undefined)(?:[?#]|$)/i.test(url)))]
    .slice(0,8).map(url=>({url,name:'产品视频'}));
}
function captureAlibabaDetail(){
  const text=(document.body?.innerText||'').slice(0,200000);
  if(/captcha|验证码|verify you are human|security verification/i.test(text)) return {error:'页面要求登录或安全验证，请人工处理后重试。'};
  const productId=(location.href.match(/_(\d+)\.html/)||[])[1]||'';
  const corePairs=coreIndustryRows();
  const importantPairs=importantRows();
  const packagingPairs=attributeRows(attributeGroup(/^(包装和发货信息|Packaging and shipping information|Packaging and delivery)$/i));
  return {
    product_id:productId,
    category:breadcrumbCategory(),
    core_industry_attributes:formatPairs(corePairs),
    important_attributes:formatPairs(importantPairs),
    packaging_information:formatPairs(packagingPairs),
    shipping_information:shippingRows(),
    photos:detailPhotos(),
    videos:detailVideos(),
  };
}
function closest1688Card(link){
  const imageSearchCard=link?.closest?.('[class*="searchOfferWrapper"]');
  if(imageSearchCard) return imageSearchCard;
  if(link?.matches?.('a.search-offer-item,a.search-offer-wrapper')) return link;
  if(link?.querySelector?.('[class*="titleText"],[class*="priceItem"]')) return link;
  let node=link;
  let fallback=link.parentElement;
  for(let i=0;i<10&&node?.parentElement;i++,node=node.parentElement){
    const text=(node.innerText||'').trim();
    const offerCount=node.querySelectorAll?.('a[href*="detail.1688.com"],a[href*="/offer/"],a[href*="offerId="]').length||0;
    if(text.length>20&&text.length<1800&&offerCount===1&&/[¥￥]\s*[\d,.]+/.test(text)) return node;
    if(offerCount===1&&text.length<2500) fallback=node;
  }
  return fallback;
}
function extract1688OfferId(link,card,url){
  const direct=(url.match(/\/offer\/(\d+)(?:\.html)?/i)||url.match(/[?&](?:offerId|id)=(\d+)/i)||[])[1];
  if(direct) return direct;
  for(const node of card?.querySelectorAll?.('[href],[data-href],[data-offer-id],[data-offerid]')||[]){
    const value=[node.getAttribute('href'),node.getAttribute('data-href'),node.getAttribute('data-offer-id'),node.getAttribute('data-offerid')].filter(Boolean).join(' ');
    const found=(value.match(/\/offer\/(\d+)(?:\.html)?/i)||value.match(/(?:offerId|offer_id|data-offer-id)[=:\"']+(\d+)/i)||[])[1];
    if(found) return found;
  }
  const html=card?.innerHTML||link?.outerHTML||'';
  return (html.match(/(?:offerId|offer_id|offer-id)(?:%3D|[=:\"']+)(\d{8,})/i)||[])[1]||'';
}
function extract1688AiOpportunity(){
  const labels=['需求识别','下游售价','图搜趋势'];
  const nodes=[...document.querySelectorAll('div,section,article,aside')];
  let container=nodes
    .filter(node=>/AI商机识别/.test(node.innerText||''))
    .filter(node=>labels.some(label=>(node.innerText||'').includes(label)))
    .sort((left,right)=>(left.innerText||'').length-(right.innerText||'').length)[0];
  const scopeText=container?.innerText||document.body?.innerText||'';
  const lines=scopeText.split('\n').map(value=>value.replace(/\s+/g,' ').trim()).filter(Boolean);
  const parts=[];
  for(const label of labels){
    const index=lines.findIndex(value=>value.includes(label));
    if(index<0) continue;
    const line=lines[index];
    let value=line.slice(line.indexOf(label)+label.length).replace(/^[：:\s-]+/,'').trim();
    if(!value&&lines[index+1]&&!/^(?:需求识别|下游售价|图搜趋势|AI商机识别)/.test(lines[index+1])) value=lines[index+1];
    if(value) parts.push(`${label}：${value}`);
  }
  return parts.join('\n');
}
function capture1688(){
  const params=new URL(location.href).searchParams;
  const candidateId=Number(params.get('pih_candidate_id')||0);
  const memberTags=params.get('filtMemberTags')||'';
  const activeMerchantFeatures=[];
  if(/(?:^|,)(?:5179713|5125953)(?:,|$)/.test(memberTags)) activeMerchantFeatures.push('实力商家');
  if(/(?:^|,)3938689(?:,|$)/.test(memberTags)) activeMerchantFeatures.push('超级工厂');
  if(/(?:^|,)5343297(?:,|$)/.test(memberTags)) activeMerchantFeatures.push('源头旗舰');
  if(candidateId) chrome.storage.local.set({last1688CandidateId:candidateId});
  const items=[],seen=new Set();
  const links=[...document.querySelectorAll(
    '[class*="searchOfferWrapper"],a.search-offer-item,a.search-offer-wrapper,a[href*="detail.1688.com"],a[href*="/offer/"],a[href*="offerId="]'
  )];
  for(const link of links){
    const url=absoluteUrl(link.getAttribute('href')||link.getAttribute('data-href')||'');
    const card=closest1688Card(link),rawText=card?.innerText||'',text=rawText.replace(/\s+/g,' ').trim();
    const id=extract1688OfferId(link,card,url);
    if(!id||seen.has(id)) continue;
    if(!text) continue;
    seen.add(id);
    const titleNode=card.querySelector('.title-text')||card.querySelector('[class*="titleText"]')||
      card.querySelector('[class*="offer-title"]')||card.querySelector('[class*="titleRow"]');
    let title=(titleNode?.getAttribute('title')||titleNode?.textContent||link.getAttribute('title')||link.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(!title){
      title=(card.innerText||'').split('\n').map(value=>value.trim()).find(value=>value.length>=4&&!/[¥￥]\s*[\d,.]+/.test(value))||`1688商品 ${id}`;
    }
    const image=card.querySelector('img.main-img,img[class*="mainImg"],[class*="offerImg"] img,[class*="offer-img"] img,img');
    const priceNode=card.querySelector('.price-item')||card.querySelector('[class*="priceItem"]')||
      card.querySelector('[class*="offer-price"]')||card.querySelector('[class*="priceRow"]');
    const price=((priceNode?.textContent||'').replace(/\s+/g,'').match(/[¥￥]?[\d,.]+(?:[-~至][\d,.]+)?/)||
      text.match(/[¥￥]\s*[\d,.]+(?:\s*[-~至]\s*[\d,.]+)?/)||[])[0]||'';
    const supplierNode=card.querySelector('[class*="shopName"]');
    const supplierLink=[...card.querySelectorAll('a')].find(a=>{
      try{
        const host=new URL(a.href).hostname;
        return host.endsWith('.1688.com')&&!/^(?:air|work|detail|detail\.m)\.1688\.com$/i.test(host)&&!a.href.includes('/offer/');
      }catch{return false;}
    });
    const supplierName=(supplierNode?.getAttribute('title')||supplierNode?.textContent||supplierLink?.getAttribute('title')||supplierLink?.textContent||'').replace(/\s+/g,' ').trim();
    const badgeText=`${text} ${[...card.querySelectorAll('.badge-text,.desc-text,[class*="badgeText"],[class*="descText"],[title],[alt]')]
      .map(node=>node.getAttribute('title')||node.getAttribute('alt')||node.textContent||'').join(' ')}`;
    const merchantIconSources=[...card.querySelectorAll('img')]
      .map(node=>absoluteUrl(node.currentSrc||node.getAttribute('src')||node.getAttribute('data-src')||''));
    const detectedFeatures=[];
    if(merchantIconSources.some(src=>src.includes('O1CN018b1zLS1wEurq13P6s_!!6000000006277'))) detectedFeatures.push('实力商家');
    if(merchantIconSources.some(src=>src.includes('O1CN01LlGIs925kozzBmKoL_!!6000000007565'))) detectedFeatures.push('超级工厂');
    if(merchantIconSources.some(src=>src.includes('O1CN01Yld5me1p6x0mZ6FZ6_!!6000000005312'))) detectedFeatures.push('源头旗舰店');
    const merchantFeatures=[...new Set(detectedFeatures)].join('、')||'普通商家';
    const merchantJoinTime=(badgeText.match(/(?:诚信通\s*\d+\s*年|\d+\s*年诚信通|经营\s*\d+\s*年|入驻\s*\d+\s*年|成立\s*\d+\s*年)/)||[])[0]||'';
    const phone=(text.match(/(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8})/)||[])[0]||'';
    const moqMatch=text.match(/(?:起批|起订|≥)\s*([\d,.]+)\s*(?:件|个|套|台|双|箱|只|米|千克|公斤|pcs?)/i);
    const salesNode=[...card.querySelectorAll('[class*="descText"]')]
      .find(node=>/^\s*\d+(?:\.\d+)?(?:万)?\+?\s*(?:件|笔|人付款|已售)\s*$/i.test(node.textContent||''));
    const sales=(salesNode?.textContent||
      (text.match(/(?:成交|已售|销量|复购率)[^¥￥]{0,30}/i)||[])[0]||'').replace(/\s+/g,'').trim();
    const rawLines=rawText.split('\n').map(value=>value.replace(/\s+/g,' ').trim()).filter(Boolean);
    const aiParts=[];
    for(const label of ['需求识别','下游售价','图搜趋势']){
      const lineIndex=rawLines.findIndex(value=>value.includes(label));
      if(lineIndex<0) continue;
      const line=rawLines[lineIndex];
      let value=line.slice(line.indexOf(label)+label.length).replace(/^[：:\s-]+/,'').trim();
      if(!value&&rawLines[lineIndex+1]&&!/^(?:需求识别|下游售价|图搜趋势|AI商机识别)/.test(rawLines[lineIndex+1])){
        value=rawLines[lineIndex+1];
      }
      if(value) aiParts.push(`${label}：${value}`);
    }
    const location=(text.match(/广东|浙江|江苏|福建|山东|河北|河南|上海|北京|天津|安徽|湖北|湖南|江西|四川|重庆|广西|辽宁|吉林|黑龙江|山西|陕西|云南|贵州|甘肃|青海|海南|内蒙古|宁夏|新疆|西藏|香港|澳门|台湾/)||[])[0]||'';
    // Advertising redirect shells sometimes expose an offer id without the
    // visible product/supplier/price fields. Never push those incomplete rows.
    if(!title||!supplierName||!price) continue;
    const detailLink=[...card.querySelectorAll('a[href],a[data-href]')].find(node=>{
      const href=absoluteUrl(node.getAttribute('href')||node.getAttribute('data-href')||'');
      return new RegExp(`^https?://detail\\.1688\\.com/offer/${id}\\.html(?:[?#]|$)`,'i').test(href);
    });
    const actualProductUrl=absoluteUrl(
      detailLink?.getAttribute('href')||detailLink?.getAttribute('data-href')||''
    );
    items.push({
      product_id:id,product_title:title,
      product_url:actualProductUrl||`https://detail.1688.com/offer/${id}.html`,
      main_image:absoluteUrl(image?.currentSrc||image?.getAttribute('data-lazy-src')||image?.getAttribute('src')||'')
        .replace(/_\.(?:webp|avif)(?=\?|#|$)/i,''),
      supplier_name:supplierName,supplier_url:supplierLink?.href||'',
      merchant_features:merchantFeatures,
      merchant_join_time:merchantJoinTime.replace(/\s+/g,''),
      contact_phone:phone,contact_details:phone?'页面公开联系电话':'页面未公开显示联系电话',
      supplier_location:location,price_text:price?(price.startsWith('¥')||price.startsWith('￥')?price:`¥${price}`):'',
      min_price:number(price,/([\d,.]+)/),
      moq:moqMatch?Number(moqMatch[1].replace(/,/g,'')):1,sales_text:sales,
      ai_business_opportunity:aiParts.join('\n'),
      captured_at:new Date().toISOString(),
    });
    if(items.length>=100) break;
  }
  const pageInsight=extract1688AiOpportunity();
  const insightRef=params.get('imageId')||params.get('imageIdList')||params.get('keywords')||`search-${candidateId}`;
  return {
    candidate_id:candidateId,
    items,
    source_insights:pageInsight?[{
      source_platform:'1688',external_ref:`search:${insightRef}`,
      source_product_name:'1688搜索商机',source_url:location.href,
      insight_content:pageInsight,
    }]:[],
  };
}
function captureYiwugo(){
  const params=new URL(location.href).searchParams;
  const candidateId=Number(params.get('pih_candidate_id')||0);
  if(candidateId) chrome.storage.local.set({lastYiwugoCandidateId:candidateId});
  const items=[],seen=new Set();
  const links=[...document.querySelectorAll('a[href*="/product/detail/"]')];
  for(const link of links){
    const url=absoluteUrl(link.getAttribute('href')||'');
    const id=(url.match(/\/product\/detail\/(\d+)\.html/i)||[])[1]||'';
    if(!id||seen.has(id)) continue;
    let card=link;
    for(let i=0;i<8&&card?.parentElement;i++,card=card.parentElement){
      const count=card.querySelectorAll('a[href*="/product/detail/"]').length;
      const cardText=(card.innerText||'').trim();
      if(count===1&&cardText.length>20&&cardText.length<1500) break;
    }
    const rawText=card?.innerText||link.innerText||'';
    const lines=rawText.split('\n').map(value=>value.replace(/\s+/g,' ').trim()).filter(Boolean);
    const text=lines.join(' ');
    let title=(link.getAttribute('title')||link.getAttribute('aria-label')||lines[0]||'').trim();
    if(title.length>300) title=lines.find(value=>value.length>=4&&!/价格联系商家|\d+\s*[.]\s*\d+\s*元/.test(value))||`义乌购商品 ${id}`;
    const priceMatch=text.match(/(\d+(?:\s*[.]\s*\d+)?)(?:\s*[~至-]\s*(\d+(?:\s*[.]\s*\d+)?))?\s*元/);
    const minPrice=priceMatch?Number(priceMatch[1].replace(/\s+/g,'')):0;
    const priceText=priceMatch?`¥${priceMatch[1].replace(/\s+/g,'')}${priceMatch[2]?` ~ ${priceMatch[2].replace(/\s+/g,'')}`:''}`:'价格联系商家';
    const supplierLink=[...card.querySelectorAll('a[href*="/hu/"]')].find(node=>(node.textContent||'').trim());
    const supplierName=(supplierLink?.textContent||'').replace(/\s+/g,' ').trim();
    const joinTime=(text.match(/\d+\s*年/)||[])[0]||'';
    const sales=(text.match(/成交\s*\d+(?:\.\d+)?(?:万)?\s*(?:双|件|个|套|台|箱|只|对|笔)?/)||[])[0]||'';
    const moq=(text.match(/(\d+(?:\.\d+)?)\s*(?:双|件|个|套|台|箱|只|对)起购/)||[])[1]||'1';
    const image=card.querySelector('img');
    const locationLine=lines.find(value=>/义乌国际商贸城|浙江省|广东省|福建省|江苏省|山东省/.test(value))||'';
    if(!title||!supplierName||!url) continue;
    seen.add(id);
    items.push({
      source_platform:'yiwugo',product_id:id,product_title:title,product_url:url,
      main_image:absoluteUrl(image?.currentSrc||image?.getAttribute('data-src')||image?.getAttribute('src')||''),
      supplier_name:supplierName,supplier_url:absoluteUrl(supplierLink?.getAttribute('href')||''),
      merchant_features:'普通商家',merchant_join_time:joinTime,
      supplier_location:locationLine,price_text:priceText,min_price:minPrice,
      moq:Number(moq)||1,sales_text:sales,contact_details:'页面未公开显示联系电话',
      captured_at:new Date().toISOString(),
    });
    if(items.length>=100) break;
  }
  return {candidate_id:candidateId,items,source_insights:[]};
}
function rememberCandidateContext(){
  const params=new URL(location.href).searchParams;
  const from1688=Number(params.get('pih_candidate_id')||0);
  if(from1688){
    if(location.hostname.endsWith('yiwugo.com')) chrome.storage.local.set({lastYiwugoCandidateId:from1688});
    else chrome.storage.local.set({last1688CandidateId:from1688});
    return;
  }
  if(!location.hostname.endsWith('odoo.com')) return;
  const recordId=Number((location.pathname.match(/\/odoo\/action-\d+\/(\d+)/)||[])[1]||0);
  if(recordId&&/(?:1688)?货源研判/.test(document.body?.innerText||'')){
    chrome.storage.local.set({last1688CandidateId:recordId});
    chrome.storage.local.set({lastYiwugoCandidateId:recordId});
  }
}
async function uploadSourcingReferenceImage(){
  const params=new URL(location.href).searchParams;
  if(!location.hostname.endsWith('1688.com')&&!location.hostname.endsWith('yiwugo.com')) return;
  // Only the dedicated Odoo image-search action may upload and submit an image.
  // A remembered candidate ID must never turn an ordinary keyword page into an image search.
  if(params.get('pih_search_mode')!=='image') return;
  const saved=await chrome.storage.local.get(['endpoint','token']);
  const candidateId=Number(params.get('pih_candidate_id')||0);
  if(!candidateId||!saved.endpoint||!saved.token) return;
  const searchGuard=`pihSourcingImageSearched:${location.hostname}:${candidateId}`;
  if(sessionStorage.getItem(searchGuard)==='1') return;
  const match=saved.endpoint.match(/^(.*\/product-intelligence\/v1\/)ingest\/(\d+)\/?$/);
  if(!match) return;
  const imageUrl=`${match[1]}sourcing-image/${match[2]}/${candidateId}`;
  if(location.hostname.endsWith('yiwugo.com')){
    // A URL supplied by Odoo is processed automatically by YiwuGo. Do not
    // inject it again or click Search a second time.
    if(params.get('url')){
      sessionStorage.setItem(searchGuard,'1');
      return;
    }
    try{
      const infoUrl=`${match[1]}sourcing-image-info/${match[2]}/${candidateId}`;
      const response=await fetch(infoUrl,{credentials:'omit',headers:{'Authorization':`Bearer ${saved.token}`}});
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      const info=await response.json();
      if(!info?.image_url) throw new Error('Missing image URL');
      let urlInput=null;
      for(let i=0;i<40&&!urlInput;i++){
        urlInput=[...document.querySelectorAll('input[type="text"],input:not([type])')]
          .find(node=>/(粘贴图片链接|图片链接)/.test(node.placeholder||''));
        if(!urlInput) await new Promise(resolve=>setTimeout(resolve,250));
      }
      if(!urlInput) throw new Error('未找到义乌购图片链接输入框');
      const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;
      setter?.call(urlInput,info.image_url);
      urlInput.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
      urlInput.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
      await new Promise(resolve=>setTimeout(resolve,300));
      const searchButton=[...document.querySelectorAll('button,[role="button"],a,div,span')]
        .filter(node=>(node.textContent||'').replace(/\s+/g,'').trim()==='搜索图片')
        .filter(node=>node.getClientRects().length>0)
        .sort((left,right)=>left.children.length-right.children.length)[0];
      if(!searchButton) throw new Error('未找到义乌购搜索图片按钮');
      searchButton.click();
      sessionStorage.setItem(searchGuard,'1');
    }catch(error){
      console.warn('LightLink: YiwuGo reference image search failed',error);
    }
    return;
  }
  let input=null;
  for(let i=0;i<40&&!input;i++){
    input=document.querySelector('input[type="file"][accept*="image"],input[type="file"]');
    if(!input){
      const camera=[...document.querySelectorAll('button,a,[role="button"],span,i')]
        .find(node=>/(以图搜|图片搜索|搜图|camera)/i.test(node.getAttribute('aria-label')||node.getAttribute('title')||node.textContent||node.className||''));
      camera?.click();
      await new Promise(resolve=>setTimeout(resolve,250));
    }
  }
  if(!input) return;
  try{
    const response=await fetch(imageUrl,{credentials:'omit',headers:{'Authorization':`Bearer ${saved.token}`}});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob=await response.blob();
    if(blob.type!=='image/jpeg') throw new Error(`Unexpected content type: ${blob.type||'unknown'}`);
    const bytes=new Uint8Array(await blob.arrayBuffer());
    let binary='';
    for(let offset=0;offset<bytes.length;offset+=32768){
      binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
    }
    const result=await chrome.runtime.sendMessage({
      type:'PIH_SOURCING_MAIN_WORLD_UPLOAD',data:btoa(binary),mimeType:'image/jpeg',
    });
    if(!result?.ok) throw new Error(result?.error||'货源页面上传失败');
    if(result.searched) sessionStorage.setItem(searchGuard,'1');
  }catch(error){
    console.warn('LightLink: sourcing reference image upload failed',error);
  }
}
uploadSourcingReferenceImage();
rememberCandidateContext();
chrome.runtime.onMessage.addListener((message,_sender,sendResponse)=>{
  if(message?.type==='PIH_CAPTURE_V108') sendResponse({items:captureAlibaba()});
  if(message?.type==='PIH_DETAIL_V110') sendResponse(captureAlibabaDetail());
  if(message?.type==='PIH_1688_CAPTURE_V109') sendResponse(capture1688());
  if(message?.type==='PIH_YIWUGO_CAPTURE_V100') sendResponse(captureYiwugo());
});
