# 个人 Gmail 上传 Drive：OAuth 客户端配置

用个人 Gmail 时，需要先建一个「OAuth 2.0 客户端 ID（桌面应用）」，下载 JSON 并改名为 `client_secrets.json`，再运行一次 `script/authorize_drive.py` 完成浏览器登录。下面按步骤说明。

---

## 1. 打开 Google Cloud Console

- 浏览器打开：<https://console.cloud.google.com/>
- 用你的 **Gmail 账号**登录（和要用 Drive 上传的是同一个账号）

---

## 2. 选择/确认项目

- 顶部导航栏有一个**项目选择器**（显示当前项目名称）
- 点击它，选择你**已经在用 Gemini 的那个项目**（例如 `elevated-dynamo-467108-a5`）
- 若没有项目，先点「新建项目」建一个，再选它

---

## 3. 进入「凭据」页面

- 左侧菜单点 **「API 和服务」**（或 "APIs & Services"）
- 在子菜单里点 **「凭据」**（"Credentials"）
- 会看到「创建凭据」「OAuth 同意屏幕」等

---

## 4. 先配置 OAuth 同意屏幕（若还没配过）

- 若你从没配过 OAuth，需要先点 **「OAuth 同意屏幕」**（在「凭据」页左侧或上方）
- **用户类型**选 **「外部」**（External）→ 下一步
- **应用信息**：应用名称随便填（如 `Visocode Drive`），用户支持邮箱填你的 Gmail → 保存并继续
- **范围**：若没有「添加或移除范围」，可先跳过；若有，添加 `https://www.googleapis.com/auth/drive` → 保存并继续
- **测试用户**：点「添加用户」，把你的 Gmail 加进去 → 保存并继续
- 回到 **「凭据」** 页面继续下面步骤

---

## 5. 创建 OAuth 2.0 客户端 ID

- 在「凭据」页面，点顶部 **「+ 创建凭据」**
- 下拉选 **「OAuth 2.0 客户端 ID」**（"OAuth client ID"）

---

## 6. 选择应用类型与名称

- **应用类型**：选 **「桌面应用」**（"Desktop app"）
- **名称**：随便填，例如 `Visocode Desktop` 或 `Drive Upload`
- 点 **「创建」**

---

## 7. 下载 JSON 并放到项目里

- 创建成功后，会弹出「OAuth 客户端已创建」对话框，或你在凭据列表里会看到新的一条「OAuth 2.0 客户端 ID」
- 点该客户端右侧的 **「下载」** 图标（或名称进去后右上角「下载 JSON」）
- 浏览器会下载一个类似 `client_secret_xxxxx.json` 的文件
- 把该文件**移动到项目根目录**：
  ```
  /Users/liangyue/02_Projects/Jobhunting/Projects/Visocode/
  ```
- **重命名**为（注意是复数 secrets）：
  ```
  client_secrets.json
  ```
- 确保路径是：`Visocode/client_secrets.json`（和 `app.py`、`run.py` 同级）

---

## 8. 启用 Drive API（若未启用）

- 左侧「API 和服务」→ **「已启用的 API 和服务」**（或「库」）
- 搜索 **Google Drive API**
- 点进去，若显示「启用」就点一下；若显示「管理」说明已启用，不用改

---

## 9. 本地跑一次授权

在项目根目录执行：

```bash
cd /Users/liangyue/02_Projects/Jobhunting/Projects/Visocode
python script/authorize_drive.py
```

- 会打开默认浏览器，用你的 Gmail 登录并点「允许」
- 成功后项目根目录会多一个 **`token.json`**
- 之后上传都会用这个 token（你的账号、你的 Drive），无需再点

---

## 常见问题

| 问题 | 处理 |
|------|------|
| 找不到「OAuth 2.0 客户端 ID」 | 先完成「OAuth 同意屏幕」并选「外部」 |
| 登录时提示「应用未验证」 | 测试模式下可点「高级」→「前往 xxx（不安全）」继续，仅自己用没问题 |
| 没有「下载 JSON」 | 在凭据列表里点该 OAuth 客户端名称进去，在详情页找「下载」或「下载 JSON」 |
| 运行 authorize_drive 报错找不到 client_secrets | 确认文件名是 `client_secrets.json` 且放在**项目根**（和 app.py 同级） |

---

配置好后，`client_secrets.json` 和 `token.json` 不要提交到 git（已写在 `.gitignore`）。
