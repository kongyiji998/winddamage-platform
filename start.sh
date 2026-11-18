#!/usr/bin/env bash
set -eu

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
port=${GRADIO_SERVER_PORT:-7860}
if [[ ! $port =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    echo "GRADIO_SERVER_PORT 须为 1 到 65535 之间的整数。" >&2
    exit 1
fi
export GRADIO_SERVER_PORT="$((10#$port))"
screen_url="http://127.0.0.1:$GRADIO_SERVER_PORT/screen#farm"
open_browser=false
if [[ ${1:-} == --open ]]; then
    open_browser=true
    shift
fi

open_screen() {
    xdg-open "$screen_url" >/dev/null 2>&1 || echo "请用浏览器打开 $screen_url"
}

if (: >/dev/tcp/127.0.0.1/"$GRADIO_SERVER_PORT") 2>/dev/null; then
    # 只复用本目录的服务；另一份项目也可能占用同一个端口。
    listener=$(ss -Hltnp "sport = :$GRADIO_SERVER_PORT" 2>/dev/null || true)
    if [[ $listener =~ pid=([0-9]+) ]]; then
        pid=${BASH_REMATCH[1]}
        if [[ "$(readlink "/proc/$pid/cwd" || true)" == "$(pwd -P)" ]] &&
           grep -Fzxq -- 'server.py' "/proc/$pid/cmdline" && (( $# == 0 )); then
            echo "平台已运行：$screen_url"
            if "$open_browser"; then open_screen; fi
            exit 0
        fi
    fi
    echo "端口 $GRADIO_SERVER_PORT 已被占用。请检查占用进程，或通过 GRADIO_SERVER_PORT 指定其他端口。" >&2
    exit 1
fi

infer_python="$HOME/.venvs/winddamage-infer/bin/python"
if [[ ! -x $infer_python ]]; then
    infer_python="$(command -v python || command -v python3)" || {
        echo "请先激活已安装项目依赖的 Python 环境。" >&2
        exit 1
    }
fi
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export GRADIO_ANALYTICS_ENABLED="${GRADIO_ANALYTICS_ENABLED:-False}"
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}${no_proxy:+,$no_proxy}"
export no_proxy="$NO_PROXY"
if "$open_browser"; then
    (
        if curl --noproxy '*' --fail --silent --output /dev/null --retry 60 \
                --retry-connrefused --retry-delay 1 --max-time 3 "$screen_url"; then
            open_screen
        fi
    ) &
fi
exec "$infer_python" server.py "$@"
