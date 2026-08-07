# BBBUE-MCP-Server

极简 UE 编辑器 socket MCP：在**正在运行的 UE 编辑器**内开一个本地 socket，
AI/外部脚本通过 `127.0.0.1:9876` 发送 Python 代码，UE 在主线程执行并回送 JSON 结果。

不依赖 headless `UnrealEditor-Cmd`，无 stdout 日志污染，无 DLL 锁问题。

## 组成

| 文件 | 作用 |
|---|---|
| `BBBUE_McpServer.py` | 在 UE 编辑器 Python 控制台运行一次，启动 socket 服务 |
| `BBBUE_McpClient.py` | 外部/AI 端，连接服务并执行代码 |

## 启动服务

在 UE 编辑器的 Python 控制台（Output Log 底部切到 Python）执行一次：

```python
import sys
sys.path.insert(0, r"E:\CodexWorkPlace\BBBUE-MCP-Server")
import BBBUE_McpServer
BBBUE_McpServer.start()
```

看到 `LogPython: [BBBUE-MCP] listening on 127.0.0.1:9876` 即成功。

## 调用

### Python

```python
import sys
sys.path.insert(0, r"E:\CodexWorkPlace\BBBUE-MCP-Server")
from BBBUE_McpClient import McpClient

client = McpClient()
result = client.exec("""
import unreal
asset = unreal.EditorAssetLibrary.load_asset('/Game/BBBC/BBBABP_0')
name = asset.get_name() if asset else None
""")
print(result)
```

### 命令行

```powershell
python BBBUE_McpClient.py "import unreal; print(unreal.SystemLibrary.get_engine_version())"
```

## 协议

换行分隔的 JSON：

- 请求 `{"id": 1, "code": "<python 源码>"}`
- 成功 `{"id": 1, "ok": true, "locals": {...}}`
- 失败 `{"id": 1, "ok": false, "error": "...", "traceback": "..."}`

## 设计说明

- socket accept/recv 在后台守护线程，只把请求入队；
- `exec` 通过 `unreal.register_slate_post_tick_callback` 在 UE 主线程执行，
  保证调用 `unreal` API（编辑器/资产操作）线程安全；
- 单连接、请求-响应，避免并发改资产；
- 返回值中可 JSON 序列化的局部变量放在 `locals`，不可序列化的用 `repr`。

