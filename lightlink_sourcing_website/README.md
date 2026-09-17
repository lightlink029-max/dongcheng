# LightLink Global Sourcing 网站

本模块把采购代理网站作为独立 Odoo Website 运行，并绑定到“LightLink 全球采购服务运营项目”。公开页面来自用户提供的私有本地网站镜像，但不是把静态目录直接挂到线上：构建工具会去重、移除脚本和跟踪代码、重写内部链接与素材路径，再把页面正文和元数据导入 Odoo 数据库。

## 安装或升级结果

- 独立网站类型固定为“采购代理网站”，首页为 `/sourcing`。
- 网站绑定运营项目 ID 5，结构化询盘继续进入 Odoo CRM 与采购需求。
- 本地镜像的有效页面按规范网址去重后导入为 `ll.sourcing.content.page` 记录。
- 页面标题、公开路径、正文、发布状态与页脚可在后台编辑。
- 头部导航保持本地参考站的栏目层级，链接到数据库页面。
- 页面内的旧品牌名称在构建阶段统一为 `LightLink Global Sourcing`。
- 原采购站演示服务、图片资产、指标、评价、付款和页脚记录在迁移时删除；产品、CRM、采购、销售和项目数据不删除。
- 英文为默认语言，简体中文继续使用 Odoo 原生翻译和 OdooTranslate 管理。

## 后台维护入口

进入“网站运营中心 → 采购与工厂网站管理”：

- “网站总览与切换”：维护网站身份、语言、域名、项目绑定和页脚源码。
- “网站头部导航”：维护菜单名称、层级、顺序和链接。
- “镜像页面内容”：按标题、公开路径或页面类型检索页面，编辑正文并控制发布。
- “采购询盘”：查看公开表单生成的 CRM 线索和结构化采购需求。

页面正文使用 Odoo HTML 编辑器保存。修改后的记录不会因为日常访问而被本地文件覆盖；只有显式执行新的版本迁移或手动调用镜像同步方法才会重新导入。

## 公开路由

- 首页：`/sourcing`
- 镜像页面：`/sourcing/site/<原始路径>`
- 采购需求：`/sourcing/request`

例如：

- `/sourcing/site/our-products`
- `/sourcing/site/our-products/bags-sourcing`
- `/sourcing/site/blog/c-import-from-china-guide`
- `/sourcing/site/find-china-sourcing-agents-company`
- `/sourcing/site/yiwu-china`

旧的 `/sourcing/products`、`/sourcing/about` 等入口保留兼容跳转，避免历史链接失效。

## 重新生成数据包

在开发机运行：

```powershell
python lightlink_sourcing_website/tools/build_local_mirror_bundle.py `
  "D:\Codex\2026-09-09\lightlink-recovery\research\jingsourcing\mirror\jingsourcing.com" `
  "D:\Codex\2026-08-27\wo\work\product-hub-production2\lightlink_sourcing_website"
```

生成内容包括 `data/mirror_pages.json.gz` 和 `static/mirror/`。不要在生产服务器直接抓取外部网站。
