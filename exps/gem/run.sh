#!/bin/bash

if [ -f "/dfs/data/sbin/setup.sh" ]; then
    source /dfs/data/sbin/setup.sh
fi

SCRIPT_DIR=$(cd $(dirname ${BASH_SOURCE[0]}) &>/dev/null && pwd)

PROJECT_ROOT=$(cd $(dirname ${SCRIPT_DIR})/.. &>/dev/null && pwd)

echo "Project Root: ${PROJECT_ROOT}"

cd "${PROJECT_ROOT}"

VLLM_CONFIG="${SCRIPT_DIR}/../commons/config/vllm_config4.yaml"
VLLM_LOG="${PROJECT_ROOT}/logs/vllm_server.log"
mkdir -p "${PROJECT_ROOT}/logs"
PORT=8000

source /dfs/data/uv-venv/modelscope/bin/activate

nohup uv run vllm serve --config "$VLLM_CONFIG" > "$VLLM_LOG" 2>&1 &

deactivate

VLLM_PID=$!
echo "✅ vLLM Server PID: $VLLM_PID"
echo "📝 Logs are being written to: $VLLM_LOG"

cleanup() {
    echo ""
    echo "======================================================="
    echo "🧹 Cleaning up..."
    if ps -p $VLLM_PID > /dev/null; then
        echo "🔪 Killing vLLM Server (PID: $VLLM_PID)..."
        kill $VLLM_PID
    else
        echo "⚠️ vLLM Server is not running."
    fi
    echo "👋 Done."
    echo "======================================================="
}
# 注册 trap，在 EXIT 信号（脚本退出）时触发 cleanup
trap cleanup EXIT

echo "⏳ Waiting for vLLM to load model and open port $PORT..."
start_wait=$(date +%s)
timeout=600 # 设置最大等待时间，例如 600秒 (10分钟)

while true; do
    # 检查端口是否通，并且返回 HTTP 200 (检查 /v1/models 接口)
    # 也可以简单用 nc -z localhost $PORT 检查端口，但 curl 更稳健（确保模型加载完）
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/v1/models | grep -q "200"; then
        echo "✅ Server is up and ready!"
        break
    fi

    # 检查进程是否意外挂掉
    if ! ps -p $VLLM_PID > /dev/null; then
        echo "❌ vLLM process died unexpectedly. Check $VLLM_LOG for details."
        exit 1
    fi

    # 超时检查
    current_time=$(date +%s)
    elapsed=$((current_time - start_wait))
    if [ $elapsed -ge $timeout ]; then
        echo "❌ Timeout waiting for server to start."
        exit 1
    fi

    sleep 5
    echo -n "."
done
echo ""

uv run exps/gem/process_data.py

uv run -m gem.cli.checkpoint_analyzer \
    syn_data/checkpoint.db

uv run -m gem.cli.trajectory_to_qwen_messages \
    syn_data/final_trajectories.jsonl \
    syn_data/messages_fc.jsonl

exit 0