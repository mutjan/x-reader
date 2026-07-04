#!/bin/bash
# x-reader 服务管理脚本

PLIST_NAME="com.lobsterai.xreader"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$HOME/Documents/LobsterAI/lzw/x-reader/logs"

case "$1" in
    start)
        echo "启动x-reader服务..."
        launchctl start $PLIST_NAME
        echo "服务已启动"
        ;;

    stop)
        echo "停止x-reader服务..."
        launchctl stop $PLIST_NAME
        echo "服务已停止"
        ;;

    restart)
        echo "重启x-reader服务..."
        launchctl stop $PLIST_NAME
        sleep 2
        launchctl start $PLIST_NAME
        echo "服务已重启"
        ;;

    status)
        echo "x-reader服务状态:"
        launchctl list | grep $PLIST_NAME
        echo ""
        echo "服务端口占用:"
        lsof -i :8081 2>/dev/null || echo "端口8081未被占用"
        ;;

    logs)
        echo "显示最近20行日志:"
        echo "=== 标准输出 ==="
        tail -20 "$LOG_DIR/server.log"
        echo ""
        echo "=== 错误输出 ==="
        tail -20 "$LOG_DIR/server_error.log"
        ;;

    logs-tail)
        echo "实时监控日志 (按Ctrl+C退出):"
        tail -f "$LOG_DIR/server.log" "$LOG_DIR/server_error.log"
        ;;

    enable)
        echo "设置开机自启动..."
        launchctl load -w $PLIST_PATH
        echo "已设置开机自启动"
        ;;

    disable)
        echo "取消开机自启动..."
        launchctl unload -w $PLIST_PATH
        echo "已取消开机自启动"
        ;;

    *)
        echo "x-reader 服务管理脚本"
        echo "用法: $0 [命令]"
        echo ""
        echo "可用命令:"
        echo "  start      启动服务"
        echo "  stop       停止服务"
        echo "  restart    重启服务"
        echo "  status     查看状态"
        echo "  logs       查看最近日志"
        echo "  logs-tail  实时监控日志"
        echo "  enable     设置开机自启动"
        echo "  disable    取消开机自启动"
        ;;
esac
