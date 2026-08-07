from datetime import datetime


def get_current_time() -> str:
    """获取当前服务器时间。返回格式：YYYY-MM-DD HH:MM:SS。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")