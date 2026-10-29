# GPT-Load 台湾订阅出口部署

这是为现有 Render 服务准备的自定义镜像源码，尚未部署，也尚未使用真实订阅验证。当前电脑未安装 Docker，容器构建与实际连通性需要在 GitHub Actions / Render 验证。

镜像包含 GPT-Load 2.0.0-rc.44、Mihomo v1.19.33 和进程启动脚本。代理端口 7890 与控制端口 9090 仅供容器内部使用；Render 对外服务端口为 10000。

## 1. 准备订阅链接

从机场后台复制 Clash / Mihomo / Clash Meta 格式的 HTTPS 订阅链接。使用该链接时，机场应返回包含 `proxies:` 的 YAML，而不是只有 base64 编码的通用节点列表。

在 Clash Verge 中正常使用的订阅通常可以作为起点，但仍需检查机场是否根据客户端或 User-Agent 返回不同格式。此配置下载订阅时发送 `User-Agent: Clash.Meta`。无需向任何在线订阅转换网站提交链接。

## 2. 上传源码并构建镜像

在 GitHub 新建公开仓库，例如 `gpt-load-taiwan`。上传此目录内容，使 Dockerfile、start.py 位于仓库根目录，工作流位于 `.github/workflows/image.yml`。不要把整个 gpt-load-taiwan 目录再嵌套一层。订阅链接与所有密钥仅填在 Render。

默认分支使用 main。若网页上传漏掉隐藏目录，可在 GitHub 使用 Add file → Create new file，文件名填写 `.github/workflows/image.yml`，粘贴本包同名文件内容。

推送至 main 后，打开 Actions → Build container。等待构建成功。第一次运行可能需要手动启用 Actions；工作流使用仓库自带的 GITHUB_TOKEN 推送镜像，无需添加机场凭据。

打开个人主页 → Packages → 对应镜像 → Package settings，将软件包可见性设为 Public，让 Render 可以匿名拉取。源码及镜像不含机场凭据。

镜像地址为：

```text
ghcr.io/你的github用户名/gpt-load-taiwan:taiwan-v1
```

用户名与仓库名使用小写。若首次构建显示 permission_denied，请检查仓库 Actions 是否允许该工作流写入 Packages，以及是否有同名旧包限制了仓库访问。

## 3. 在现有 Render 服务加入订阅 Secret File

打开 https://dashboard.render.com/web/srv-dbcr452vcj2c73fjg9og/env 。

Environment → Secret Files → Add Secret File：

- Filename：`subscription.txt`
- Contents：一行完整的 Clash / Mihomo HTTPS 订阅链接，不加引号。

保存。此操作可能先重新部署当前旧镜像，旧镜像不会使用这个文件。

在 Environment Variables 加入：

```text
NODE_FILTER=台湾.*07.*家宽
```

它按截图中的名字匹配「台湾 07 家宽」，应只匹配一个节点。若机场实际节点名使用繁体或别的编号，请按实际名称修改正则。脚本会在零匹配、多匹配或出口检查失败时阻止 GPT-Load 启动。

保留现有 AUTH_KEY、ENCRYPTION_KEY 和 DATABASE_DSN 的原值，尤其是 ENCRYPTION_KEY。它用于解密已保存的账号授权。保留 PORT=10000 和外部 Neon 数据库连接。

## 4. 更换现有 Render 服务镜像

打开现有服务 Settings，在 Image / Image URL 处把镜像地址改为第 2 步生成的 ghcr.io 地址。保留 Free 方案及 `/health` 健康检查路径。若 Docker Command 中填写了其他命令，清空它，让镜像自身的启动入口生效。

保存并部署。此次变更沿用现有服务及数据库，服务网址仍为 https://gpt-load-cloud.onrender.com/ 。切换期间可能短暂不可用。

日志预期依次出现：

```text
正在加载订阅并匹配指定台湾节点……
已选定订阅中的单个台湾节点。
台湾出口检查通过：country=TW ip=...
```

之后应出现 GPT-Load 启动及数据库连接日志，最终 Render 显示 Live。脚本使用 Cloudflare 的 trace 接口检查出口，其地区判断与 Anthropic 的判断可能有差异。

## 5. 将 Claude 账号明确绑定到本地代理

登录 GPT-Load，在「代理」页面新增 HTTP 代理，地址为：

```text
http://127.0.0.1:7890
```

将该代理应用到 Claude Pro 分组及其 Claude 账号。若已有其他显式代理配置，也应检查它们；凭据或分组的显式代理可能覆盖环境代理设置。此端口仅在换成新镜像后存在。

镜像启动脚本同时为 GPT-Load 设置 HTTP_PROXY 和 HTTPS_PROXY。未设置显式代理的 HTTP 上游请求也会使用该出口；Neon 的 PostgreSQL TCP 连接仍直连数据库。

## 6. 验证

检查以下项目后再确认完成：

1. Render 构建及部署成功，日志显示 country=TW。
2. https://gpt-load-cloud.onrender.com/health 返回 status=ok。
3. 后台仍显示已授权的 Claude 账号和原分组。
4. 使用已有访问密钥发送一条简短 Claude 请求，并检查成功响应及请求日志。
5. 手动重启一次，再检查启动时的台湾出口、原账号和调用结果。

512 MB 免费实例同时运行两个程序，需要观察内存是否足够。Render 休眠后，每次唤醒都需要重新下载订阅并检查出口；冷启动时间可能增加。节点密码轮换会在每日订阅更新或重新部署时获取；出现节点错误时可先手动重新部署。

## 回退

如果新镜像无法启动，可把 Image URL 改回：

```text
ghcr.io/tbphp/gpt-load:2.0.0-rc.44
```

同时移除 GPT-Load 中绑定的 `http://127.0.0.1:7890` 代理，恢复此前的代理设置；旧镜像不运行 Mihomo。若曾手动在 Render 添加 HTTP_PROXY / HTTPS_PROXY 等变量，也需恢复。保留数据库与 ENCRYPTION_KEY。

回退后的 Claude 请求会按恢复后的设置出站，未配置代理时使用 Render 出口。

## 参考

- https://wiki.metacubex.one/config/proxy-providers/
- https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.33
- https://render.com/docs/deploying-an-image
- https://render.com/docs/configure-environment-variables
