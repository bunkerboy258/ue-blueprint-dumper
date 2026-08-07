"""
BBBUE MCP Client — 连接运行在 UE 编辑器内的 socket 服务并执行 Python 代码。

用法：
    from BBBUE_McpClient import McpClient
    client = McpClient()
    result = client.exec("import unreal; unreal.log('hello')")
    print(result)

也可作为命令行：
    python BBBUE_McpClient.py "import unreal; print(unreal.EngineVersion)"
"""
import json
import socket
import sys

_HOST = "127.0.0.1"
_PORT = 9876


class McpClient:
    """与 BBBUE_McpServer 通信的极简客户端。"""

    def __init__(self, host: str = _HOST, port: int = _PORT, timeout: float = 60.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._next_id = 1

    def exec(self, code: str, timeout: float = None):
        """发送一段 Python 代码给 UE 执行，返回响应 dict。

        返回:
            {"id": n, "ok": True,  "locals": {...}}
            {"id": n, "ok": False, "error": ..., "traceback": ...}
        """
        req_id = self._next_id
        self._next_id += 1

        sock = socket.create_connection((self.host, self.port), timeout=timeout or self.timeout)
        try:
            body = (json.dumps({"id": req_id, "code": code}, ensure_ascii=False) + "\n").encode("utf-8")
            sock.sendall(body)

            buffer = b""
            sock.settimeout(timeout or self.timeout)
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    raise ConnectionError("server closed connection")
                buffer += chunk
                if b"\n" in buffer:
                    line, _ = buffer.split(b"\n", 1)
                    return json.loads(line.decode("utf-8"))
        finally:
            sock.close()


def main():
    if len(sys.argv) < 2:
        print('usage: python BBBUE_McpClient.py "<python code>"')
        sys.exit(1)
    code = sys.argv[1]
    client = McpClient()
    result = client.exec(code)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

