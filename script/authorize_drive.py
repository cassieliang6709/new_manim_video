"""
一次性：用你的个人 Gmail 登录，把 refresh token 存到 token.json。
之后上传会用你的账号、你的 Drive 空间，不再需要服务账号/共享盘。

步骤：
1. 打开 Google Cloud Console → 你的项目 → 凭据 → 创建凭据 → OAuth 2.0 客户端 ID
2. 应用类型选「桌面应用」，名称随意 → 创建
3. 下载 JSON，重命名为 client_secrets.json，放到项目根目录
4. 在项目根执行: python script/authorize_drive.py
5. 浏览器会打开，用你的 Gmail 登录并授权
6. 完成后项目根会生成 token.json，不要提交到 git
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CLIENT_SECRETS = ROOT / "client_secrets.json"
TOKEN_JSON = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    if not CLIENT_SECRETS.exists():
        print("未找到 client_secrets.json")
        print("请到 GCP 控制台创建 OAuth 2.0 客户端 ID（桌面应用），下载 JSON 并放到项目根，命名为 client_secrets.json")
        sys.exit(1)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), scopes=SCOPES)
    creds = flow.run_local_server(port=0)
    data = {
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": SCOPES,
    }
    with open(TOKEN_JSON, "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, indent=2)
    print(f"已保存到 {TOKEN_JSON}，之后上传将使用你的 Drive。勿提交此文件到 git。")


if __name__ == "__main__":
    main()
