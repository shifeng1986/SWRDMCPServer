"""
操作日志处理器模块

提供按天生成日志文件、按周归档的操作日志处理器。
支持保留三个月的日志，便于审计。
"""

import os
import logging
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler


def format_timestamp() -> str:
    """生成可读的时间戳字符串，格式：2026-05-15 15:23:06.316+08:00（本地时间，标注时区）"""
    now = datetime.now()
    # 计算 UTC+8 时区偏移
    tz_offset = "+08:00"
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}{tz_offset}"


class WeeklyTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    按天生成日志文件，按周归档的日志处理器
    
    特点：
    - 每天生成一个新的日志文件（格式：operation_YYYY-MM-DD.log）
    - 每周的日志文件放在同一个文件夹中（格式：week_YYYY-MM-DD）
    - 自动清理超过保留期的日志文件
    """

    def __init__(
        self,
        base_dir: str,
        filename_prefix: str = "operation",
        retention_days: int = 90,
        encoding: str = "utf-8",
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 90,
    ):
        """
        初始化日志处理器
        
        Args:
            base_dir: 日志基础目录
            filename_prefix: 日志文件名前缀
            retention_days: 保留天数（默认90天，约三个月）
            encoding: 文件编码
            when: 轮转时间间隔（默认为每天午夜）
            interval: 轮转间隔
            backupCount: 备份文件数量
        """
        self.base_dir = base_dir
        self.filename_prefix = filename_prefix
        self.retention_days = retention_days
        
        # 确保基础目录存在
        os.makedirs(base_dir, exist_ok=True)
        
        # 获取当前日期的日志文件路径
        current_log_path = self._get_current_log_path()
        
        # 确保周文件夹存在（父类 __init__ 会尝试打开文件，所以必须先创建目录）
        week_dir = os.path.dirname(current_log_path)
        os.makedirs(week_dir, exist_ok=True)
        
        # 初始化父类
        super().__init__(
            current_log_path,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
        )
        
        # 执行一次日志清理
        self._cleanup_old_logs()

    def _get_current_log_path(self) -> str:
        """获取当前日志文件的完整路径"""
        today = datetime.now()
        
        # 计算本周一的日期（用于确定周文件夹）
        monday = today - timedelta(days=today.weekday())
        week_folder = f"week_{monday.strftime('%Y-%m-%d')}"
        
        # 构建日志文件名
        log_filename = f"{self.filename_prefix}_{today.strftime('%Y-%m-%d')}.log"
        
        # 构建完整路径
        return os.path.join(self.base_dir, week_folder, log_filename)

    def _cleanup_old_logs(self):
        """清理超过保留期的日志文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            deleted_count = 0
            
            # 遍历所有周文件夹
            for week_folder in os.listdir(self.base_dir):
                week_folder_path = os.path.join(self.base_dir, week_folder)
                
                # 跳过非目录文件
                if not os.path.isdir(week_folder_path):
                    continue
                
                # 解析周文件夹的日期
                try:
                    if week_folder.startswith("week_"):
                        date_str = week_folder[5:]  # 去掉 "week_" 前缀
                        folder_date = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        # 如果周文件夹的日期超过保留期，删除整个文件夹
                        if folder_date < cutoff_date:
                            import shutil
                            shutil.rmtree(week_folder_path)
                            deleted_count += 1
                            continue
                except ValueError:
                    # 文件夹名称格式不正确，跳过
                    continue
                
                # 删除该周文件夹内的过期日志文件
                for log_file in os.listdir(week_folder_path):
                    log_file_path = os.path.join(week_folder_path, log_file)
                    
                    # 只处理日志文件
                    if not log_file.endswith('.log'):
                        continue
                    
                    # 解析日志文件日期
                    try:
                        if log_file.startswith(f"{self.filename_prefix}_"):
                            date_str = log_file[len(self.filename_prefix)+1:-4]  # 去掉前缀和 .log
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            
                            # 如果日志文件日期超过保留期，删除
                            if file_date < cutoff_date:
                                os.remove(log_file_path)
                                deleted_count += 1
                    except ValueError:
                        # 文件名格式不正确，跳过
                        continue
            
            if deleted_count > 0:
                # 记录清理日志（使用标准输出避免循环）
                print(f"[操作日志清理] 已删除 {deleted_count} 个过期日志文件")
                
        except Exception as e:
            # 清理失败不应该影响日志记录
            print(f"[操作日志清理失败] {str(e)}")

    def doRollover(self):
        """执行日志轮转"""
        # 在轮转前检查是否需要清理旧日志
        self._cleanup_old_logs()
        
        # 调用父类的轮转方法
        super().doRollover()
        
        # 更新日志文件路径为新的日期
        new_log_path = self._get_current_log_path()
        
        # 如果新路径与当前路径不同，更新流
        if self.baseFilename != new_log_path:
            if self.stream:
                self.stream.close()
            # 确保新目录存在
            new_dir = os.path.dirname(new_log_path)
            os.makedirs(new_dir, exist_ok=True)
            self.baseFilename = new_log_path
            self.stream = self._open()


class DebugLogForwardHandler(logging.Handler):
    """
    将操作日志记录转发到调试日志记录器的处理器
    
    当 operation_logger 记录日志时，自动将相同内容同步到 debug_logger，
    确保操作日志内容在调试日志中也可追溯。
    """

    def __init__(self, debug_logger: logging.Logger, level: int = logging.NOTSET):
        super().__init__(level)
        self._debug_logger = debug_logger

    def emit(self, record: logging.LogRecord) -> None:
        """将日志记录转发到调试日志记录器"""
        try:
            # 获取原始消息
            msg = self.format(record)

            # 根据操作日志的级别映射到调试日志的对应级别
            if record.levelno >= logging.CRITICAL:
                self._debug_logger.critical(msg)
            elif record.levelno >= logging.ERROR:
                self._debug_logger.error(msg)
            elif record.levelno >= logging.WARNING:
                self._debug_logger.warning(msg)
            elif record.levelno >= logging.INFO:
                self._debug_logger.info(msg)
            else:
                self._debug_logger.debug(msg)
        except Exception:
            self.handleError(record)


def setup_operation_logger() -> logging.Logger:
    """
    设置操作日志记录器
    
    Returns:
        logging.Logger: 操作日志记录器
    """
    from config import (
        OPERATION_LOG_LEVEL,
        OPERATION_LOG_DIR,
        OPERATION_LOG_ENCODING,
        OPERATION_LOG_RETENTION_DAYS,
        OPERATION_FILE_FORMAT,
        OPERATION_FILE_DATE_FORMAT,
    )
    
    logger = logging.getLogger("mcp_operation")
    
    # 如果已经配置过处理器，直接返回
    if logger.handlers:
        return logger
    
    logger.setLevel(OPERATION_LOG_LEVEL)
    
    # 创建操作日志处理器（按天生成，按周归档）
    operation_handler = WeeklyTimedRotatingFileHandler(
        base_dir=OPERATION_LOG_DIR,
        filename_prefix="operation",
        retention_days=OPERATION_LOG_RETENTION_DAYS,
        encoding=OPERATION_LOG_ENCODING,
        when="midnight",
        interval=1,
        backupCount=OPERATION_LOG_RETENTION_DAYS,
    )
    
    operation_handler.setLevel(OPERATION_LOG_LEVEL)
    
    # 操作日志使用简单的 JSON 格式（不含时间戳，时间戳在 JSON 内容中）
    operation_formatter = logging.Formatter(OPERATION_FILE_FORMAT)
    operation_handler.setFormatter(operation_formatter)
    
    logger.addHandler(operation_handler)

    # 添加调试日志转发处理器：将操作日志内容同步到 debug_logger
    # 注意：这里延迟获取 debug_logger 以避免循环导入
    debug_logger = logging.getLogger("mcp_debug")
    forward_handler = DebugLogForwardHandler(debug_logger, level=OPERATION_LOG_LEVEL)
    forward_handler.setFormatter(operation_formatter)
    logger.addHandler(forward_handler)
    
    return logger


def setup_debug_logger() -> logging.Logger:
    """
    设置调试日志记录器
    
    Returns:
        logging.Logger: 调试日志记录器
    """
    from config import (
        DEBUG_LOG_LEVEL,
        DEBUG_LOG_FILE,
        DEBUG_MAX_BYTES,
        DEBUG_BACKUP_COUNT,
        DEBUG_LOG_ENCODING,
        DEBUG_CONSOLE_LEVEL,
        DEBUG_CONSOLE_FORMAT,
        DEBUG_CONSOLE_DATE_FORMAT,
        DEBUG_FILE_LEVEL,
        DEBUG_FILE_FORMAT,
        DEBUG_FILE_DATE_FORMAT,
    )
    
    logger = logging.getLogger("mcp_debug")
    
    # 如果已经配置过处理器，直接返回
    if logger.handlers:
        return logger
    
    logger.setLevel(DEBUG_LOG_LEVEL)
    
    # 确保日志目录存在
    log_dir = os.path.dirname(DEBUG_LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(DEBUG_CONSOLE_LEVEL)
    console_formatter = logging.Formatter(
        DEBUG_CONSOLE_FORMAT,
        datefmt=DEBUG_CONSOLE_DATE_FORMAT
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器 - 按大小轮转
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        DEBUG_LOG_FILE,
        maxBytes=DEBUG_MAX_BYTES,
        backupCount=DEBUG_BACKUP_COUNT,
        encoding=DEBUG_LOG_ENCODING,
    )
    file_handler.setLevel(DEBUG_FILE_LEVEL)
    file_formatter = logging.Formatter(
        DEBUG_FILE_FORMAT,
        datefmt=DEBUG_FILE_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


__all__ = [
    "WeeklyTimedRotatingFileHandler",
    "setup_operation_logger",
    "setup_debug_logger",
]
