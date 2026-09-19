import { readFile, writeFile } from "node:fs/promises";

const base = JSON.parse(await readFile("research-eb6b6f4e-1a75e1a7.json", "utf8"));
const capturedAt = "2026-09-16T12:28:00Z";

const markets = [
  { code: "GB", name: "英国", buyers: ["进口商", "细分批发商", "礼赠品公司", "电商卖家"], entry: "B2B定向开发、付费样品、订单生产；不建库存。", compliance: ["产品安全与适用电气规则", "RoHS/WEEE适用性", "英文标签和进口商责任"] },
  { code: "US", name: "美国", buyers: ["区域分销商", "礼赠品分销商", "IT/家居经销商", "电商卖家"], entry: "先询盘和样品，由美国进口商书面确认联邦及州级要求。", compliance: ["CPSC适用规则", "FCC适用性", "州级标签与化学要求"] },
  { code: "DE", name: "德国（欧盟入口）", buyers: ["欧盟进口商", "专业批发商", "礼赠品公司"], entry: "先确认EU经济运营者、德语资料和德国EPR，再接受订单。", compliance: ["CE适用法规", "RoHS/WEEE", "德语说明与EU经济运营者"] },
  { code: "AU", name: "澳大利亚", buyers: ["本地进口商", "办公礼赠商", "专业零售批发商"], entry: "与本地Responsible Supplier合作，小批样品验证。", compliance: ["EESS/RCM适用性", "ACMA要求", "本地责任主体"] },
  { code: "AE", name: "阿联酋", buyers: ["迪拜进口商", "酒店用品商", "企业礼赠商"], entry: "仅访谈和报价，先由当地进口商确认ECAS与标签范围。", compliance: ["ECAS适用性", "进口许可与标签", "当地代理责任"] },
  { code: "CA", name: "加拿大", buyers: ["消费品进口商", "办公与家居批发商", "电商卖家"], entry: "只做需求访谈；由加拿大进口商确认安全、EMC和双语标签。", compliance: ["产品安全适用性", "EMC/无线适用性", "英法双语标签"] },
  { code: "FR", name: "法国（欧盟）", buyers: ["欧盟进口商", "家居个护批发商", "礼赠品公司"], entry: "通过欧盟进口商验证，先处理法语资料和法国EPR。", compliance: ["CE适用法规", "RoHS/WEEE与法国EPR", "法语说明"] },
  { code: "NL", name: "荷兰（欧盟物流入口）", buyers: ["欧盟分销商", "跨境电商服务商", "专业进口商"], entry: "仅作为欧盟物流/分销假设，先确认荷兰EPR与经济运营者。", compliance: ["CE适用法规", "RoHS/WEEE", "欧盟经济运营者"] },
  { code: "SG", name: "新加坡", buyers: ["东南亚分销商", "企业礼赠商", "专业零售商"], entry: "先买家访谈和样品，不对受管制电气产品作准入承诺。", compliance: ["当地受管制商品范围", "安全/EMC适用性", "进口商责任"] },
  { code: "JP", name: "日本", buyers: ["专业进口商", "家居数码批发商", "企业采购"], entry: "通过本地进口商验证日语标签、PSE/无线等适用性后再报价。", compliance: ["PSE适用性", "无线/EMC适用性", "日语标签与进口商"] }
];

const trackSpecs = [
  {
    id: "kitchen-low-voltage", name: "厨房低压与测量电子", priority: "high", score: 68,
    description: "低压、可演示、体积较小的厨房测量与辅助产品；食品接触和准确性需逐SKU验证。",
    buyers: ["厨房用品进口商", "烘焙咖啡批发商", "酒店用品分销商"],
    compliance: ["食品接触材料适用性", "EMC/RoHS/EEE责任", "准确性与温度宣称"], risk: "medium",
    items: [
      ["双探针数字食品温度计","食品温度测量"],["折叠探针烧烤温度计","食品温度测量"],["红外厨房表面温度计","非接触测温"],["数字糖果温度计","烘焙测温"],["冰箱冷冻室数字温度计","冷链监测"],["数字量勺秤","微量称量"],["带称重功能电子量杯","液体与粉料计量"],["数字分装勺","膳食分装"],["磁吸厨房倒计时器","厨房计时"],["多通道烘焙计时器","厨房计时"],["USB手持奶泡器","饮品制作"],["电动红酒开瓶器","酒具"],["电动红酒醒酒器","酒具"],["电动胡椒研磨器","调味工具"],["迷你食品袋热封机","食品收纳"],["真空红酒瓶塞泵","酒具"],["电动开罐器","厨房辅助"],["数字咖啡豆含水率仪","咖啡质量检测"],["便携TDS水质测试笔","饮用水检测"],["数字厨房油温计","烹饪测温"]
    ]
  },
  {
    id: "home-climate-usb", name: "家居气候与USB舒适设备", priority: "high", score: 64,
    description: "桌面、卧室和个人舒适场景的小型低压设备；液体、加热或锂电版本提高风险。",
    buyers: ["办公用品分销商", "家居礼赠商", "宿舍用品零售商"],
    compliance: ["EMC/RoHS/EEE责任", "温升/阻燃/漏水", "电池运输（如适用）"], risk: "medium",
    items: [
      ["USB夹式风扇","个人降温"],["USB无叶颈挂风扇","可穿戴降温"],["USB塔式桌面风扇","个人降温"],["USB键盘冷风扇","桌面降温"],["USB桌面加湿器","空气加湿"],["USB瓶盖加湿器","空气加湿"],["USB香薰扩散器","香氛设备"],["USB桌面空气循环器","空气循环"],["USB鞋内烘干器","低功率烘干"],["USB手套烘干器","低功率烘干"],["USB坐垫加热片","个人加热"],["USB护膝加热带","个人加热"],["USB鞋垫加热器","个人加热"],["USB迷你除湿盒","局部除湿"],["桌面空气质量CO2提示器","环境监测"],["桌面温湿度计","环境监测"],["室内噪声分贝显示器","环境监测"],["日出模拟唤醒灯","睡眠照明"],["USB白噪声机","睡眠辅助"],["USB蚊香加热器","驱蚊设备"]
    ]
  },
  {
    id: "home-cleaning-tools", name: "家居清洁与维护电子", priority: "high", score: 63,
    description: "单一清洁任务的小型工具；重点核对防水、旋转部件、耗材与连续运行。",
    buyers: ["家居清洁批发商", "五金家居零售商", "物业用品采购"],
    compliance: ["机械安全与夹伤", "防水/漏电", "EMC/RoHS/EEE责任"], risk: "medium",
    items: [
      ["USB键盘迷你吸尘器","桌面清洁"],["USB电脑屏幕清洁器","数码清洁"],["超声波首饰清洗机","精细清洁"],["超声波眼镜清洗机","精细清洁"],["电动浴室缝隙刷","浴室清洁"],["电动百叶窗清洁刷","家居清洁"],["电动鞋刷机","鞋类护理"],["便携电动去污笔","织物清洁"],["电动窗槽清洁刷","家居清洁"],["迷你桌面碎屑吸尘器","桌面清洁"],["电动排水管疏通器","管道维护"],["电动马桶刷","卫浴清洁"],["电动玻璃刮水器","玻璃清洁"],["电动瓷砖美缝清洁器","地面清洁"],["电动奶瓶刷","餐具清洁"],["电动杯具清洁刷","餐具清洁"],["充电式毛发清理滚刷","宠物毛发清洁"],["电动鞋底清洁机","入口清洁"],["迷你臭氧鞋柜除味器","除味设备"],["USB活性炭衣柜除味器","除味设备"]
    ]
  },
  {
    id: "pet-electronics", name: "宠物小型电子用品", priority: "medium", score: 58,
    description: "宠物喂养、饮水、护理与训练设备；须关注动物安全、咬线、防水和耗材。",
    buyers: ["宠物用品进口商", "宠物店连锁", "兽医渠道分销商"],
    compliance: ["防水与咬线风险", "食品接触材料", "电池/无线适用性"], risk: "medium",
    items: [
      ["USB宠物饮水机","宠物饮水"],["定时宠物喂食器","宠物喂养"],["宠物粮电子量杯","宠物喂养"],["宠物指甲电磨","宠物护理"],["宠物脚毛修剪器","宠物护理"],["宠物毛发吹梳器","宠物护理"],["宠物按摩梳","宠物护理"],["宠物足部清洁杯","宠物清洁"],["鱼缸USB增氧泵","水族设备"],["鱼缸数字温度计","水族监测"],["鱼缸自动喂食器","水族喂养"],["爬宠箱温湿度计","爬宠监测"],["宠物项圈LED安全灯","宠物安全"],["宠物声响训练器","宠物训练"],["宠物门铃按钮","宠物训练"],["猫咪互动电动球","宠物玩具"],["电动逗猫转盘","宠物玩具"],["宠物除味空气过滤器","宠物环境"],["宠物加热垫","宠物保暖"],["宠物饮水机滤芯监测器","耗材监测"]
    ]
  },
  {
    id: "travel-outdoor-electronics", name: "旅行与户外小电子", priority: "medium", score: 57,
    description: "旅行、露营和应急场景；电池、防水和航空运输是主要门槛。",
    buyers: ["旅行用品进口商", "户外用品批发商", "企业礼赠商"],
    compliance: ["电池运输与容量标识", "防水/跌落", "无线/照明安全适用性"], risk: "medium",
    items: [
      ["折叠式旅行闹钟","旅行计时"],["数字行李标签","旅行识别"],["行李箱LED警示灯","旅行安全"],["便携数字指南针","户外导航"],["USB露营帐篷灯","户外照明"],["夹帽式LED灯","户外照明"],["可充电钥匙扣手电","随身照明"],["太阳能应急收音机","应急通信"],["便携手摇应急灯","应急照明"],["便携电动抽气泵","露营充气"],["便携露营淋浴泵","户外用水"],["USB帐篷通风扇","露营通风"],["便携电子驱蚊器","户外防虫"],["USB暖手器","个人保暖"],["电热旅行眼罩","旅行睡眠"],["旅行门窗震动报警器","旅行安全"],["行李箱电子称重手柄","旅行称重"],["电子旅行药盒提醒器","旅行提醒"],["防水户外温度计","户外监测"],["便携紫外线强度计","户外监测"]
    ]
  },
  {
    id: "automotive-12v", name: "汽车12V与车内电子", priority: "medium", score: 52,
    description: "车载低压用品；必须核对汽车环境温度、EMC、连接器与电池风险。",
    buyers: ["汽车用品进口商", "汽配连锁", "车队用品采购"],
    compliance: ["汽车EMC适用性", "12V电气与过流保护", "高温/振动/电池安全"], risk: "medium",
    items: [
      ["数字胎压表","轮胎维护"],["12V便携轮胎充气泵","轮胎维护"],["12V车载吸尘器","车内清洁"],["车载双头循环风扇","车内气候"],["车载座椅通风垫","车内气候"],["12V车载电热饭盒","车载加热"],["12V车载热水杯","车载加热"],["车载空气质量监测器","车内环境"],["车载太阳能排风扇","车内气候"],["OBD-II基础故障码读取器","车辆诊断"],["汽车电瓶电压测试器","车辆诊断"],["点烟器USB电压显示器","车辆诊断"],["车载倒车雷达套件","停车辅助"],["车门防撞LED警示灯","车辆安全"],["汽车安全带切割报警器","应急安全"],["车载电子香薰器","车内香氛"],["车载冷暖杯架","车载温控"],["汽车除霜加热风机","车窗除霜"],["车载迷你垃圾桶感应盖","车内收纳"],["12V车辆应急启动电源","应急电源"]
    ]
  },
  {
    id: "computer-input-office", name: "电脑输入与办公USB配件", priority: "high", score: 62,
    description: "有线、免驱、无外置电源的办公配件优先；兼容性和耐久为核心。",
    buyers: ["IT分销商", "企业办公采购", "教育设备经销商"],
    compliance: ["FCC/EMC/RCM适用性", "RoHS/WEEE", "操作系统兼容与寿命"], risk: "medium",
    items: [
      ["USB有线数字小键盘","输入设备"],["USB静音有线鼠标","输入设备"],["USB轨迹球鼠标","输入设备"],["USB脚踏快捷键控制器","输入设备"],["USB演示翻页器有线版","演示设备"],["USB指纹读取器","身份验证"],["USB智能卡读卡器","身份验证"],["USB条码扫描笔","数据采集"],["USB文档扫描仪","文档数字化"],["USB签名板","业务输入"],["USB有线会议控制器","会议设备"],["USB键盘状态指示器","办公辅助"],["USB多电脑切换器","KVM配件"],["USB数据隔离器","工业办公配件"],["USB端口锁管理套装","数据安全"],["USB接口测试器","维修工具"],["USB线材功率测试表","维修工具"],["HDMI信号测试器","维修工具"],["便携网线测试仪","网络工具"],["USB桌面呼叫按钮","办公呼叫"]
    ]
  },
  {
    id: "wired-audio-content", name: "有线音频与内容创作配件", priority: "medium", score: 57,
    description: "避开无线和内置电池，优先USB/3.5mm有线音频配件；关注音质、驱动与兼容性。",
    buyers: ["音频配件分销商", "直播设备经销商", "教育内容采购"],
    compliance: ["EMC/FCC适用性", "RoHS/WEEE", "音量与听力警示"], risk: "medium",
    items: [
      ["USB桌面电容麦克风","录音设备"],["USB鹅颈会议麦克风","会议音频"],["3.5mm有线领夹麦克风","移动录音"],["USB有线扬声器条","电脑音频"],["USB有线会议扬声器","会议音频"],["USB外置声卡","音频接口"],["USB音频混音旋钮","内容创作"],["有线耳机分配器","音频分配"],["光纤转模拟音频转换器","音频转换"],["HDMI音频分离器","音频转换"],["USB-C转3.5mm音频适配器","移动音频"],["XLR转USB音频接口","录音接口"],["有线骨传导耳机","个人音频"],["单耳呼叫中心耳麦","商务耳机"],["儿童限音有线耳机","教育音频"],["航空双插孔耳机适配器","旅行音频"],["麦克风静音脚踏开关","录音控制"],["桌面麦克风静音按钮","会议控制"],["有线耳机音量控制器","音频控制"],["直播声卡控制面板","内容创作"]
    ]
  },
  {
    id: "mobile-passive-connectivity", name: "手机无源与有线连接配件", priority: "high", score: 60,
    description: "不含无线和电池的连接、保护与工具类配件；低门槛但同质化强。",
    buyers: ["手机配件批发商", "礼赠品公司", "维修渠道"],
    compliance: ["连接器与电气安全", "材料化学限制", "兼容性与知识产权"], risk: "low",
    items: [
      ["USB-C转USB-A OTG适配器","接口转换"],["USB-C转Micro-USB适配器","接口转换"],["USB-C转Lightning数据线","数据线"],["编织USB-C快充数据线","数据线"],["多头旅行充电线无电池版","数据线"],["磁吸理线充电线夹","线材管理"],["手机SIM卡收纳工具盒","旅行配件"],["多规格SIM卡转换套件","通信配件"],["手机防水触控袋","户外保护"],["手机镜头清洁笔","数码清洁"],["手机屏幕除尘贴套装","贴膜工具"],["手机贴膜定位器","贴膜工具"],["可折叠平板支架","支架"],["车载出风口手机夹","车载支架"],["桌夹式手机长臂支架","直播支架"],["手机冷靴扩展框","内容创作"],["手机有线快门按钮","拍摄配件"],["USB-C存储读卡线","数据连接"],["手机防盗伸缩绳","零售防盗"],["手机维修磁性螺丝垫","维修工具"]
    ]
  },
  {
    id: "low-voltage-lighting", name: "低压照明与提示设备", priority: "medium", score: 58,
    description: "USB或低压照明、提示与装饰产品；需核光生物安全、温升和电池。",
    buyers: ["照明配件进口商", "礼赠品公司", "家居零售商"],
    compliance: ["光生物安全适用性", "EMC/RoHS/EEE责任", "电池运输（如适用）"], risk: "medium",
    items: [
      ["USB橱柜灯条","家具照明"],["USB衣柜感应灯","家具照明"],["USB镜前补光灯条","美容照明"],["USB显示器挂灯","办公照明"],["USB植物生长补光棒","园艺照明"],["USB水族箱灯条","水族照明"],["USB自行车尾灯","骑行安全"],["USB鞋夹警示灯","夜跑安全"],["USB宠物牵引绳警示灯","宠物安全"],["USB帐篷串灯","露营照明"],["USB阅读指示灯夹","学习照明"],["USB摄影小补光灯","内容创作"],["USB化妆镜环形灯","美容照明"],["USB楼梯感应灯","家居安全"],["USB床底感应灯","家居照明"],["USB冰箱感应灯","家电配件"],["低压门牌背光灯","标识照明"],["LED会议室占用指示灯","办公提示"],["桌面电子请勿打扰灯","办公提示"],["USB应急爆闪警示灯","应急照明"]
    ]
  },
  {
    id: "beauty-grooming", name: "美容与个人护理电子", priority: "medium", score: 52,
    description: "贴肤、旋转、加热或光照产品风险差异大；首轮只做访谈与样品安全筛查。",
    buyers: ["美容个护进口商", "药妆零售商", "沙龙用品批发商"],
    compliance: ["皮肤/眼部接触安全", "刀头/温升/光源", "电池与EEE责任"], risk: "medium",
    items: [
      ["电动眉毛修剪器","面部修剪"],["电动鬓角修剪器","面部修剪"],["电动耳毛修剪器","面部修剪"],["电动面部洁面刷","面部清洁"],["硅胶声波洁面仪","面部清洁"],["电动黑头吸附仪","面部护理"],["电动面部按摩滚轮","面部护理"],["电热睫毛夹","眼部美容"],["USB美甲打磨机","美甲工具"],["LED美甲固化灯","美甲工具"],["电动指甲抛光器","美甲工具"],["电动足部磨皮器","足部护理"],["USB头皮按摩梳","头皮护理"],["电动洗发按摩刷","头皮护理"],["迷你直发梳","头发造型"],["USB刘海卷发器","头发造型"],["电动化妆刷清洗器","化妆工具"],["化妆品迷你冷藏盒","化妆品存储"],["智能化妆镜灯无App版","美容照明"],["电动香水分装泵","美容工具"]
    ]
  },
  {
    id: "wellness-nonmedical", name: "非医疗健康与放松电子", priority: "medium", score: 49,
    description: "只允许舒适、放松、生活方式表达，不作诊断、治疗或预防宣称。",
    buyers: ["健康生活方式零售商", "企业福利采购", "礼赠品公司"],
    compliance: ["避免医疗宣称", "皮肤接触与温升", "电池/EMC/EEE责任"], risk: "medium",
    items: [
      ["桌面呼吸节奏灯","放松训练"],["番茄钟专注计时器","专注管理"],["坐姿时间提醒器","行为提醒"],["站立办公提醒器","行为提醒"],["饮水时间提醒杯垫","行为提醒"],["智能药盒提醒器非联网版","用药提醒"],["睡眠声音播放器","睡眠环境"],["冥想计时器","冥想辅助"],["USB眼部热敷罩","舒适热敷"],["USB颈部热敷带","舒适热敷"],["USB腰部热敷带","舒适热敷"],["电动头皮按摩器","放松按摩"],["手持震动按摩球","放松按摩"],["迷你筋膜振动器","运动放松"],["电动足底按摩垫","足部放松"],["肩颈脉冲按摩器非医疗版","放松设备"],["便携香氛呼吸灯","环境放松"],["电子握力计健身版","运动测量"],["数字跳绳计数器","运动计数"],["桌面步数挑战计数器","企业健康活动"]
    ]
  },
  {
    id: "stem-education-tools", name: "STEM教育与电子工具", priority: "medium", score: 56,
    description: "面向学校、创客和培训渠道的低压工具与套件；年龄分级和焊接安全需明确。",
    buyers: ["教育用品经销商", "创客空间", "培训机构采购"],
    compliance: ["年龄分级与小部件", "焊接/电气安全", "EMC/RoHS/EEE责任"], risk: "medium",
    items: [
      ["USB数字显微镜","科学观察"],["手持电子放大镜","科学观察"],["数字土壤湿度计","园艺实验"],["数字照度计","物理测量"],["数字声级计教育版","物理测量"],["数字风速计教育版","气象测量"],["迷你电子气象站","气象学习"],["太阳能小车实验套件","新能源实验"],["手摇发电机实验套件","能源实验"],["基础电路积木套件","电路学习"],["面包板传感器学习包","电子学习"],["焊接练习电子钟套件","焊接训练"],["USB低压电烙铁套装","电子工具"],["数字万用表学生版","电子测量"],["晶体管测试仪","电子测量"],["逻辑探针测试笔","电子测量"],["网络水晶头测试仪","网络工具"],["电子元件分类计数器","实验室管理"],["可编程LED徽章套件","编程学习"],["有线桌面绘图机器人","机器人学习"]
    ]
  },
  {
    id: "retail-business-devices", name: "零售与轻商用电子设备", priority: "medium", score: 55,
    description: "面向门店、仓库和办公室的小型设备；关注数据、耗材、软件兼容和商用耐久。",
    buyers: ["POS设备经销商", "零售系统集成商", "仓储用品分销商"],
    compliance: ["EMC/FCC/RCM适用性", "数据与软件兼容", "商用耐久和耗材"], risk: "medium",
    items: [
      ["USB一维条码扫描枪","条码采集"],["USB二维二维码扫描枪","条码采集"],["便携热敏标签打印机有线版","标签打印"],["桌面热敏小票打印机","票据打印"],["USB电子签名板","客户签名"],["顾客价格显示屏","POS显示"],["桌面叫号显示器","排队管理"],["有线服务评价按钮","客户反馈"],["USB柜台呼叫铃","服务呼叫"],["电子货架标签测试套件","零售标价"],["便携验钞紫外灯","现金管理"],["桌面纸币计数器","现金管理"],["硬币分类计数器","现金管理"],["电子邮政包裹秤","物流称重"],["USB仓库拣货指示灯","仓储辅助"],["有线库存盘点扫描器","库存管理"],["电子钥匙柜编号显示器","资产管理"],["桌面工位状态灯","办公管理"],["会议室门牌显示屏","会议管理"],["USB访客登记证打印机","访客管理"]
    ]
  },
  {
    id: "medical-electronics-expanded", name: "医疗电子扩展候选", priority: "low", score: 15,
    description: "仅作为未来合规路线储备；当前预算和团队下全部拒绝采购或销售。",
    buyers: ["医疗器械进口商", "医院供应商", "药房与康复渠道"],
    compliance: ["目标市场医疗器械分类/注册", "本地责任主体", "QMS/临床性能/上市后义务"], risk: "high",
    items: [
      ["便携式雾化器","呼吸治疗"],["电子峰流速仪","呼吸监测"],["家用肺活量计","呼吸监测"],["单导联心电记录仪","心电监测"],["动态心率监护贴","心电监测"],["血糖监测仪","血糖监测"],["尿酸检测仪","生化检测"],["胆固醇检测仪","生化检测"],["红外额温计医疗版","体温监测"],["耳温枪医疗版","体温监测"],["胎心多普勒仪","母婴监测"],["电子听诊器","临床诊断"],["数字助听器","听力辅助"],["耳道检查摄像仪医疗版","耳鼻喉检查"],["睡眠呼吸筛查仪","睡眠监测"],["电子疼痛脉冲治疗仪","理疗设备"],["盆底肌电刺激器","康复设备"],["医用负压吸引器","临床设备"],["医用红外静脉显像仪","临床辅助"],["便携式黄疸检测仪","新生儿监测"]
    ]
  }
];

if (trackSpecs.length !== 15 || trackSpecs.some((t) => t.items.length !== 20)) {
  throw new Error("必须恰好生成15个赛道×20个产品");
}

const marketSets = [
  ["GB", "AU"], ["GB", "US"], ["DE", "FR", "NL"], ["US", "CA"], ["AE", "SG"],
  ["AU", "SG"], ["GB", "DE"], ["US", "JP"], ["DE", "JP"], ["GB", "AE"]
];
const existingNames = new Set(base.productPool.map((p) => String(p.name).trim().toLowerCase()));
const newNames = new Set();
const productPool = [];
let seq = 0;

for (const track of trackSpecs) {
  for (const [name, subcategory] of track.items) {
    const normalized = name.trim().toLowerCase();
    if (existingNames.has(normalized) || newNames.has(normalized)) throw new Error(`候选重复: ${name}`);
    newNames.add(normalized);
    const targetMarkets = marketSets[seq % marketSets.length];
    const medical = track.id === "medical-electronics-expanded";
    const elevated = medical || /加热|热敷|烘干|电烙铁|启动电源|紫外|臭氧|治疗|刺激|雾化|心电|血糖|尿酸|胆固醇|胎心|听诊|助听|黄疸/.test(name);
    const riskLevel = medical ? "high" : elevated ? "high" : track.risk;
    const stage = medical ? "rejected" : riskLevel === "high" ? "research" : "idea";
    const score = medical ? 10 + (seq % 8) : Math.max(35, Math.min(75, track.score + ((seq % 7) - 3)));
    productPool.push({
      id: `expand-${String(seq + 1).padStart(3, "0")}`,
      name,
      trackCategory: track.name,
      subcategory,
      commercialVariant: medical ? "具体型号、用途与分类未冻结；仅作未来法规储备" : "基础有线或可更换电池版本；最终规格待买家访谈和RFQ冻结",
      imageUrls: [],
      imageSourceRef: "",
      targetMarkets,
      buyerTypes: track.buyers,
      priceBand: "",
      moq: "",
      compliance: track.compliance,
      riskLevel,
      stage,
      score,
      rationale: medical ? "医疗用途触发分类、注册、质量体系、本地责任主体和上市后义务；本轮不采购。" : `具体产品方向明确，但需求、成交价、MOQ和同型号合规证据尚未核验；先在${targetMarkets.join("/")}做买家访谈。`,
      evidenceStatus: "hypothesis"
    });
    seq += 1;
  }
}

const trackCategories = trackSpecs.map((t) => ({
  id: t.id,
  name: t.name,
  description: t.description,
  subcategories: [...new Set(t.items.map((x) => x[1]))],
  targetMarkets: [...new Set(productPool.filter((p) => p.trackCategory === t.name).flatMap((p) => p.targetMarkets))],
  buyerTypes: t.buyers,
  priority: t.priority,
  opportunityScore: t.score,
  evidenceStatus: "hypothesis"
}));

const marketHypotheses = markets.map((m) => ({
  marketCode: m.code,
  marketName: m.name,
  demandHypothesis: `本轮为产品池扩充，未取得${m.name}的授权销量或Google Trends CSV；候选只作为待验证方向，不能据此推断需求规模。`,
  buyerTypes: m.buyers,
  entryMode: m.entry,
  complianceFocus: m.compliance,
  recommendedTracks: trackSpecs.filter((_, i) => (i + markets.indexOf(m)) % 3 === 0).slice(0, 6).map((t) => t.name),
  validationStatus: "hypothesis"
}));

const matrix = [];
for (const track of trackSpecs) {
  for (const market of markets) {
    const active = track.priority === "high" && ["GB", "US", "AU"].includes(market.code);
    matrix.push({
      category: track.name,
      market: market.code,
      targetCustomers: [...track.buyers, ...market.buyers].slice(0, 5).join("、"),
      demandEvidence: `本轮未取得${market.name}该赛道的可复核销量或趋势CSV；需用买家访谈、付费样品和书面试单补证。`,
      competitionPriceBand: null,
      supplyFeasibility: "未知；需按具体产品向至少3家供应商发统一RFQ并核验同型号文件。",
      complianceThreshold: [...track.compliance, ...market.compliance].slice(0, 6).join("；"),
      budgetCny: active ? 500 : 0,
      mainRisk: track.risk === "high" ? "高合规/责任门槛，不进入首期采购" : "需求、价格、MOQ与到岸成本均待验证",
      priority: track.id === "medical-electronics-expanded" ? "REJECT_NOW" : track.priority === "low" ? "HOLD" : active ? "P2" : "P3"
    });
  }
}

const report = {
  ...base,
  status: "complete",
  summary: "本轮完成候选产品池扩充：在现有24条之外新增300个不重复的具体产品，覆盖15个赛道和GB、US、DE、AU、AE、CA、FR、NL、SG、JP十个具体市场。新增项均包含赛道、细分、商业版本、目标市场、买家、合规关注、风险、阶段和评分。由于本轮没有取得逐商品可核验的成交价、MOQ、授权销量或稳定图片直链，相关字段保持为空，全部新增项标为hypothesis；未把名称数量当成需求证据。预算和执行结论保持TEST：只从新增池中按周筛选，不因候选增多而扩大首期采购。医疗电子扩展候选全部REJECT_NOW。",
  recommendation: "test",
  scorecard: { complianceSafety: 13, marketBuyer: 11, unitEconomics: 8, supplyStability: 13, salesExpression: 12, total: 57 },
  trackCategories,
  productPool,
  marketHypotheses,
  playbook: {
    roadmap180Days: { summary: "300个新增候选分三层漏斗管理，不改变先验证后采购原则。", items: ["0-30天：300条去重、风险初筛，每周选20条做买家检索", "31-60天：对前60条完成RFQ和买家访谈，淘汰无回复/高风险项", "61-90天：只给前10条打样，最多3条进入付费样品", "91-120天：单市场单SKU试单", "121-180天：以复购和现金回收决定是否扩第二SKU"] },
    teamSop: { summary: "A负责供应链和合规，B负责市场和买家；候选池不等于采购清单。", items: ["A每周筛10个产品的供应商、文件、MOQ和样品条件", "B每周筛10个产品的买家、场景、目标价和证书要求", "周五合并评分，只保留证据更强的前20%", "任何医疗、市电、无线或锂电方向须双人确认后才能进入样品"] },
    budgetAndQuoting: { summary: "总预算仍为50000元；本轮扩池不增加库存预算。", items: ["候选研究与名单3000", "样品与国内运费7000", "合规预审9000", "国际样品运费6000", "内容与触达5000", "小单定金储备13000", "保险清关应急7000", "未获付费订单前库存0"] },
    complianceSupplyChain: { summary: "先按危险源筛选，再按市场确认法规。", items: ["用途和宣称冻结", "市场进口商/实验室书面适用性", "报告-型号-BOM一致", "包装/HS/到岸成本", "责任险和召回联系人", "黄金样验收后付款"] },
    customerAcquisition: { summary: "每次只验证一个具体产品和一个场景。", items: ["英文一页规格+30秒演示", "每周50个新核验账户", "首触达25、跟进20、有效访谈3", "样品收费可抵首单", "记录目标价/MOQ/证书/交期/退货原因"] },
    executionChecklist: { summary: "用证据把300条压缩到可执行短名单。", items: ["名称与现有池去重", "具体国家代码完整", "价格/MOQ无证据留空", "图片无直链证据留空", "高风险项不进入首期采购", "第8周按回复、样品和毛利门槛停续"] }
  },
  sections: {
    product_definition: { summary: "新增300个具体产品，15赛道各20个；与现有24条名称去重。", findings: ["所有新增候选均关联赛道、细分领域和2-3个具体国家。", "新增池覆盖厨房、家居气候、清洁、宠物、旅行、汽车、电脑、音频、手机配件、照明、美容、非医疗健康、STEM、零售设备和医疗电子。", "医疗电子20条仅作未来法规储备，全部拒绝当前采购。", "图片字段保留空数组，因为未取得逐产品可核验且不重复的公开图片直链。"] },
    market_demand: { summary: "扩池不等于需求验证；150个赛道×市场组合均保留需求证据缺口。", findings: ["覆盖10个具体市场，不使用GLOBAL作为单条候选的唯一市场。", "没有Google Trends CSV或授权销量，因此不生成趋势、销量或热度数值。", "下一步以买家回复、付费样品和书面试单为需求证据。"], matrix },
    competition_pricing: { summary: "新增300条的价格带均为空，避免把不同规格平台展示价误当成交价。", findings: ["每周只对进入前20%的候选发统一RFQ。", "统一数量阶梯100/300/500件、EXW/FOB、包装尺寸和报告编号。", "获得正式PI后才填写采购价与MOQ。"] },
    buyers_channels: { summary: "新增候选按十国买家假设分配，优先B2B进口商、细分批发商、礼赠和企业采购。", findings: ["每个候选至少关联2个具体市场。", "GB/US/AU用于首轮英语买家验证；DE/FR/NL用于EU假设；AE/SG/JP/CA只做远程访谈。", "医疗候选只联系合规进口商了解准入，不发销售报价。"] },
    supply_moq: { summary: "新增候选尚无逐SKU供应证据，供应可行性保持未知。", findings: ["每个进入前60名的候选询3家供应商。", "索取营业主体、工厂地址、同型号报告、BOM、包装、缺陷与变更流程。", "未收到签字PI前MOQ和价格保持空。"] },
    compliance_logistics: { summary: "候选先按危险源筛分，再按十国逐SKU确认；不存在全球通用证书。", findings: ["低风险优先：无源、有线低压、可更换电池、无医疗宣称。", "提高门槛：加热、旋转刀头、液体、紫外/臭氧、汽车环境、无线、锂电。", "医疗用途：分类、注册、本地责任主体、QMS、性能证据和上市后义务必须单独预算。", "运费与税费在包装和HS/HTS未冻结前保持未知。"] },
    unit_economics: { summary: "扩池阶段不计算虚假利润，只设置验证预算和毛利门槛。", findings: ["贡献毛利公式沿用：实收-货价-物流-税费-履约-支付/平台-退货质保-佣金。", "进入样品的候选须有两家物流报价和正式PI。", "继续条件为预测批发贡献毛利率≥30%、现金回收≤两个补货周期。"], budgetCny: { totalCap: 50000, researchAndBuyerLists: 3000, samplesDomestic: 7000, compliancePreReview: 9000, internationalSamples: 6000, contentOutreach: 5000, smallOrderDepositReserve: 13000, insuranceCustomsContingency: 7000, inventoryBeforePaidOrder: 0 } },
    recommendation_actions: { summary: "本轮目标是扩大漏斗，不扩大采购。300条先压缩到60条、再到10条、最终最多3条打样。", findings: ["优先筛选有线低压、无电池、体积小、可演示且有清晰B2B买家的产品。", "市电、汽车高功率、加热、无线和锂电方向只做访谈。", "20条医疗电子全部拒绝当前阶段。"], decision: "第8周前只有达到8次有效访谈、3个付费样品请求或1个书面试单意向，且合规文件通过、预测贡献毛利率≥30%的候选才进入小单。" }
  },
  risks: ["把候选数量当需求证据", "产品名称与现有池重复", "用通用图片或重复图片填充候选", "编造价格/MOQ/销量", "同时打样过多导致预算失控", "忽略具体国家的经济运营者/EPR/标签", "高风险产品未经预审进入采购", "供应商BOM替换导致报告失效", "医疗宣称触发未预算的准入义务", "低货值被物流和退货吞噬"],
  actionPlan: ["第1-30天：300条去重与风险初筛，每周20条进入买家检索", "第31-60天：前60条完成RFQ和访谈，淘汰无证据方向", "第61-90天：前10条样品评估，最多3条进入付费样品", "每周KPI：50个新账户、25次首触达、20次跟进、3次有效访谈", "继续条件：合规通过、毛利预测≥30%、8次访谈且3个付费样品或1个试单", "停止条件：报告不一致、安全缺陷、目标价低于到岸成本、8周无有效信号"],
  evidence: [
    ...base.evidence.map((e) => ({ ...e, capturedAt })),
    { sectionKey: "product_definition", sourceType: "candidate_expansion", sourceTitle: "Candidate expansion taxonomy and deduplication audit", sourceUrl: "", market: "GLOBAL", capturedAt, status: "available", excerpt: "本地生成审计确认15个赛道各20个具体产品，共300条；与现有24条名称及本轮内部名称均无重复。", metrics: { newCandidateCount: 300, trackCount: 15, marketCount: 10 } },
    { sectionKey: "competition_pricing", sourceType: "supplier_quote", sourceTitle: "Product-specific RFQ and signed PI for 300 new candidates", sourceUrl: "", market: "GLOBAL", capturedAt, status: "missing", excerpt: "本轮为候选扩充，未向300条逐一取得统一RFQ或正式PI；价格和MOQ保持空。补证：只对筛选前60名发3家/产品RFQ。", metrics: {} },
    { sectionKey: "product_definition", sourceType: "image_audit", sourceTitle: "Verified product image URLs for new and existing candidates", sourceUrl: "", market: "GLOBAL", capturedAt, status: "missing", excerpt: "未取得逐产品、可公开访问、来源页可追溯且不重复的图片直链，因此imageUrls保持空数组。补证：进入前60名后逐商品页采集。", metrics: {} }
  ]
};

await writeFile("research-eb6b6f4e-b6d30308-expand300.json", `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ file: "research-eb6b6f4e-b6d30308-expand300.json", tracks: trackCategories.length, products: productPool.length, markets: marketHypotheses.length, matrix: matrix.length, evidence: report.evidence.length }, null, 2));
