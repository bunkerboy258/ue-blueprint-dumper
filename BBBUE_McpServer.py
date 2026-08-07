"""
BBBUE MCP Server — 在运行的 UE 编辑器内启动一个极简 socket 服务。

用法（UE 编辑器 Python 控制台执行一次）：
    import sys
    sys.path.insert(0, r"E:\CodexWorkPlace\BBBUE-MCP-Server")
    import BBBUE_McpServer
    BBBUE_McpServer.start()

之后 AI/外部进程通过 127.0.0.1:9876 发送 Python 代码，服务器在 UE 主线程
通过 slate tick 执行并回送 JSON 结果。

协议（换行分隔的 JSON）：
    请求:  {"code": "<python 源码>", "id": <可选请求号>}
    响应:  {"id": ..., "ok": true,  "result": <repr>, "locals": {...}}
           {"id": ..., "ok": false, "error": <msg>, "traceback": <str>}

设计要点：
- socket 监听放在后台守护线程，只负责把请求放进队列；
- 真正的 exec 在 UE 主线程执行（通过 slate 的 on_tick 回调），
  这样调用 unreal API 不会因线程问题崩溃；
- 单连接、请求-响应模型，避免并发修改资产。
"""
import json
import socket
import threading
import traceback

import unreal

_HOST = "127.0.0.1"
_PORT = 9876

_request_queue = []
_queue_lock = threading.Lock()
_client_conn = None
_client_lock = threading.Lock()
_started = False


def _exec_in_ue(code: str, req_id):
    """在 UE 主线程执行代码，并把结果回送给客户端。"""
    global_ns = {
        "unreal": unreal,
        "__builtins__": __builtins__,
    }
    local_ns = {}
    payload = {"id": req_id, "ok": True}
    try:
        exec(code, global_ns, local_ns)
        serializable = {}
        for key, val in local_ns.items():
            if key.startswith("_"):
                continue
            try:
                json.dumps(val)
                serializable[key] = val
            except (TypeError, ValueError):
                serializable[key] = repr(val)
        payload["locals"] = serializable
    except Exception as exc:  # noqa: BLE001
        payload["ok"] = False
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc()

    body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with _client_lock:
        conn = _client_conn
    if conn is not None:
        try:
            conn.sendall(body)
        except OSError:
            pass


def _on_tick(delta_seconds: float):
    """slate tick 回调：在 UE 主线程消费请求队列。"""
    while True:
        with _queue_lock:
            if not _request_queue:
                return
            code, req_id = _request_queue.pop(0)
        _exec_in_ue(code, req_id)


def _client_loop(conn: socket.socket):
    """后台线程：读取客户端发来的每一行 JSON 请求并入队。"""
    global _client_conn
    buffer = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                code = msg.get("code", "")
                req_id = msg.get("id")
                with _queue_lock:
                    _request_queue.append((code, req_id))
    except OSError:
        pass
    finally:
        with _client_lock:
            if _client_conn is conn:
                _client_conn = None
        try:
            conn.close()
        except OSError:
            pass
        unreal.log("[BBBUE-MCP] client disconnected")


def _accept_loop(server_sock: socket.socket):
    """后台线程：接受客户端连接（同时只服务一个）。"""
    global _client_conn
    while True:
        try:
            conn, addr = server_sock.accept()
        except OSError:
            return
        with _client_lock:
            _client_conn = conn
        unreal.log(f"[BBBUE-MCP] client connected: {addr}")
        threading.Thread(target=_client_loop, args=(conn,), daemon=True).start()


def start(port: int = _PORT):
    """启动 socket 服务并注册 slate tick。重复调用安全。"""
    global _started
    if _started:
        unreal.log("[BBBUE-MCP] already running")
        return

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((_HOST, port))
    server_sock.listen(1)
    server_sock.setblocking(True)

    threading.Thread(target=_accept_loop, args=(server_sock,), daemon=True).start()

    # 注册主线程 tick，用于在 UE 主线程执行请求
    unreal.register_slate_post_tick_callback(_on_tick)

    _started = True
    unreal.log(f"[BBBUE-MCP] listening on {_HOST}:{port}")


def main():
    start()


if __name__ == "__main__":
    main()
