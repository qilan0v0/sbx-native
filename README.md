# Sbx Native

本仓库提供不同运行环境的 sing-box native 启动器，用于部署 VMess Ws + Argo、VLESS Reality、Hysteria2、TUIC、AnyTLS、SOCKS5 等代理，只有主进程，没有子进程。

请选择对应环境查看说明：

| 环境 | 说明文档 | 入口文件 |
| --- | --- | --- |
| Java | [JAVA.md](JAVA.md) | [java/src/main/java/dev/sbxnative/App.java](java/src/main/java/dev/sbxnative/App.java) |
| Node.js | [NODE.md](NODE.md) | [nodejs/index.js](nodejs/index.js) |
| Python | [PYTHON.md](PYTHON.md) | [python/app.py](python/app.py) |

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `UPLOAD_URL` | 空 | Merge-sub 上传地址。填写后可上传订阅或节点。 |
| `PROJECT_URL` | 空 | 项目公网 URL。用于上传订阅和自动保活。 |
| `AUTO_ACCESS` | `false` | 设置为 `true` 时向保活服务提交 `PROJECT_URL`。 |
| `YT_WARPOUT` | `false` | 设置为 `true` 时强制 YouTube 走 WARP 出站规则。 |
| `FILE_PATH` | `.npm` | 运行目录，存放动态库、配置、订阅和临时文件。 |
| `SUB_PATH` | `sub` | 订阅token，例如 `/sub`。 |
| `UUID` | `0a6568ff-ea3c-4271-9020-450560e10d63` | 节点 UUID。建议自行修改。 |
| `NEZHA_SERVER` | 空 | 哪吒服务端地址。v1：`nezha.xxx.com:8008` v0: `nezha.xxx.com` |
| `NEZHA_PORT` | 空 | 哪吒 v0 agent 端口；v1 留空。 |
| `NEZHA_KEY` | 空 | 哪吒 v1 的 `NZ_CLIENT_SECRET` 或 v0 agent 密钥。 |
| `ARGO_DOMAIN` | 空 | Cloudflare 固定隧道域名。为空时使用临时隧道。 |
| `ARGO_AUTH` | 空 | Cloudflare tunnel token 或 TunnelSecret JSON。 |
| `ARGO_PORT` | `8001` | Argo隧道端口，使用token需在cloudflare里设置一致 |
| `S5_PORT` | 空 | SOCKS5 入站端口。为空不启用。 |
| `TUIC_PORT` | 空 | TUIC 入站端口。为空不启用。 |
| `HY2_PORT` | 空 | Hysteria2 入站端口。为空不启用。 |
| `ANYTLS_PORT` | 空 | AnyTLS 入站端口。为空不启用。 |
| `REALITY_PORT` | 空 | VLESS Reality 入站端口。为空不启用。 |
| `CFIP` | `saas.sin.fan` | VMess Argo 节点中的优选域名或 IP。 |
| `CFPORT` | `443` | `CFIP` 对应端口。 |
| `PORT` | `3000` | HTTP 订阅服务监听端口。 |
| `NAME` | 空 | 节点名称前缀。 |
| `CHAT_ID` | 空 | Telegram chat id。 |
| `BOT_TOKEN` | 空 | Telegram bot token。`CHAT_ID` 和 `BOT_TOKEN` 都存在才推送。 |
| `DISABLE_ARGO` | `false` | 设置为 `true` 时禁用 Argo |


## 目录结构

```text
.
├── java/
│   ├── pom.xml
│   └── src/main/java/dev/sbxnative/App.java
├── nodejs/
│   ├── index.js
│   └── package.json
├── python/
│   ├── app.py
│   └── requirements.txt
├── JAVA.md
├── NODE.md
├── PYTHON.md
└── README.md
```

## 简要说明

- 请先确认端口在部署平台开放并未被占用。
- sing-box版本由官方1.13.13正式版源码构建，公开透明，如有疑问，可以自行构建替换。
- Reality 会首次生成并持久化 `keypair.properties`，后续重启会复用同一对 key。
- HY2、TUIC、AnyTLS 会使用自签证书，客户端需要开启 `allow_insecure` 或等效选项。
- 请在符合当地法律法规和服务商规则的前提下使用。
