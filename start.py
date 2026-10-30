import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


CONTROLLER = "http://127.0.0.1:9090"
PROXY = "http://127.0.0.1:7890"
GROUP = "CLAUDE-TW"
CHILDREN = []
STOPPING = False


def stop(signum=None, frame=None):
    global STOPPING
    STOPPING = True
    for child in reversed(CHILDREN):
        if child.poll() is None:
            child.terminate()


def cleanup():
    stop()
    deadline = time.monotonic() + 8
    for child in reversed(CHILDREN):
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def make_config(subscription, secret, file_provider=False):
    provider = {
        "path": "./providers/airport.yaml",
        "filter": os.environ.get("NODE_FILTER", "台湾.*07.*家宽"),
        "health-check": {"enable": False},
    }
    if file_provider:
        provider["type"] = "file"
    else:
        provider.update({
            "type": "http",
            "url": subscription,
            "interval": 86400,
            "proxy": "DIRECT",
            "header": {"User-Agent": ["Clash.Meta"]},
        })
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "bind-address": "127.0.0.1",
        "mode": "rule",
        "ipv6": False,
        "log-level": "error",
        "external-controller": "127.0.0.1:9090",
        "secret": secret,
        "profile": {"store-selected": False},
        "proxy-providers": {"airport": provider},
        "proxy-groups": [{
            "name": GROUP,
            "type": "select",
            "proxies": ["REJECT"],
            "use": ["airport"],
        }],
        "rules": [f"MATCH,{GROUP}"],
    }


def prepare_provider(directory, snapshot_file, secret_file):
    if snapshot_file.is_file():
        try:
            snapshot = json.loads(snapshot_file.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            raise RuntimeError("固定节点配置无法读取，请检查 airport-snapshot.json。") from None
        nodes = snapshot.get("proxies") if isinstance(snapshot, dict) else None
        if not isinstance(nodes, list) or not nodes or not all(isinstance(node, dict) for node in nodes):
            raise RuntimeError("airport-snapshot.json 需要包含有效的 proxies 节点列表。")
        providers = directory / "providers"
        providers.mkdir(mode=0o700, parents=True, exist_ok=True)
        (providers / "airport.yaml").write_text(
            json.dumps({"proxies": nodes}, ensure_ascii=False), encoding="utf-8")
        print("已加载固定节点配置，启动无需下载订阅。", flush=True)
        return None, True
    if not secret_file.is_file():
        raise RuntimeError("请在 Render Secret Files 添加 airport-snapshot.json 固定节点配置。")
    subscription = secret_file.read_text(encoding="utf-8-sig").strip()
    parsed = urlsplit(subscription)
    if parsed.scheme != "https" or not parsed.hostname or any(c.isspace() for c in subscription):
        raise RuntimeError("subscription.txt 需要填写一条完整的 HTTPS Clash/Mihomo 订阅链接。")
    return subscription, False


def control(secret, path, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = Request(CONTROLLER + path, data=data,
                  method="GET" if value is None else "PUT",
                  headers={"Authorization": "Bearer " + secret,
                           "Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(req, timeout=4) as response:
        body = response.read()
        return json.loads(body) if body else {}


def verify_egress():
    result = subprocess.run(
        ["curl", "--silent", "--show-error", "--fail", "--noproxy", "",
         "--proxy", PROXY, "--connect-timeout", "10", "--max-time", "20",
         "https://www.cloudflare.com/cdn-cgi/trace"],
        capture_output=True, text=True,
    )
    trace = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode != 0 or trace.get("loc") != "TW":
        raise RuntimeError("台湾出口检查失败。请核实 NODE_FILTER、节点连通性及出口地区；Cloudflare 检查服务也可能暂时不可用。")
    print("台湾出口检查通过：country=TW ip=" + trace.get("ip", "unknown"), flush=True)


def main():
    os.umask(0o077)
    for key in ("AUTH_KEY", "ENCRYPTION_KEY", "DATABASE_DSN"):
        if not os.environ.get(key):
            raise RuntimeError("缺少固定环境变量：" + key)
    directory = Path("/tmp/gpt-load-mihomo")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    subscription, file_provider = prepare_provider(
        directory, Path("/etc/secrets/airport-snapshot.json"), Path("/etc/secrets/subscription.txt"))
    controller_secret = secrets.token_hex(24)
    config = directory / "config.yaml"
    config.write_text(json.dumps(make_config(subscription, controller_secret, file_provider), ensure_ascii=False), encoding="utf-8")
    proxy_env = os.environ.copy()
    for key in list(proxy_env):
        if key.lower().endswith("_proxy"):
            proxy_env.pop(key)
    child = subprocess.Popen(["/usr/local/bin/mihomo", "-d", str(directory), "-f", str(config)],
                             env=proxy_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    CHILDREN.append(child)
    print("正在加载节点并匹配指定台湾节点……", flush=True)
    selected = None
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline and not STOPPING:
        if child.poll() is not None:
            raise RuntimeError("Mihomo 启动失败，请检查订阅格式及镜像版本。")
        try:
            group = control(controller_secret, "/proxies/" + GROUP)
            candidates = [n for n in group.get("all", []) if n not in ("REJECT", "DIRECT", "COMPATIBLE")]
            if candidates:
                if len(candidates) != 1:
                    raise RuntimeError("NODE_FILTER 匹配到多个节点，请收窄到单个节点。")
                selected = candidates[0]
                control(controller_secret, "/proxies/" + GROUP, {"name": selected})
                break
        except (OSError, ValueError):
            pass
        time.sleep(2)
    if STOPPING:
        return 0
    if not selected:
        raise RuntimeError("未获取到匹配节点。请检查订阅是否为 Clash/Mihomo 格式、Render 是否能下载，以及 NODE_FILTER 是否匹配节点名。")
    print("已选定订阅中的单个台湾节点。", flush=True)
    verify_egress()
    app_env = os.environ.copy()
    app_env.update({"HTTPS_PROXY": PROXY, "HTTP_PROXY": PROXY,
                    "https_proxy": PROXY, "http_proxy": PROXY,
                    "NO_PROXY": "localhost,127.0.0.1,::1",
                    "no_proxy": "localhost,127.0.0.1,::1"})
    app = subprocess.Popen(["/app/gpt-load"], env=app_env)
    CHILDREN.append(app)
    while not STOPPING:
        if child.poll() is not None:
            raise RuntimeError("Mihomo 已退出，正在停止 GPT-Load。")
        if app.poll() is not None:
            return app.returncode or 1
        try:
            group = control(controller_secret, "/proxies/" + GROUP)
            if selected not in group.get("all", []) or group.get("now") != selected:
                raise RuntimeError("台湾节点选择已变化，正在停止 GPT-Load；请检查订阅后重新部署。")
        except (OSError, ValueError):
            raise RuntimeError("无法确认代理运行状态，正在停止 GPT-Load。") from None
        time.sleep(3)
    return 0


if __name__ == "__main__":
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    code = 1
    try:
        code = main()
    except RuntimeError as error:
        print(str(error), file=sys.stderr, flush=True)
    except Exception:
        print("启动失败，请检查订阅 Secret File 和运行环境。", file=sys.stderr, flush=True)
    finally:
        cleanup()
    sys.exit(code)
