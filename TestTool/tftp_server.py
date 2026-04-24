#!/usr/bin/env python
"""
稳定的Python TFTP服务器实现
支持大文件传输，具有重试机制和超时控制
"""
import socket
import struct
import os
import time
import sys

# TFTP服务器配置
TFTP_PORT = 69
TFTP_DIR = r"C:\firmware_upgrade"
BLOCK_SIZE = 8192  # 8KB块大小
TIMEOUT = 60  # 每个数据包的超时时间（秒）
MAX_RETRIES = 10  # 最大重试次数

# TFTP操作码
OPCODE_RRQ = 1
OPCODE_WRQ = 2
OPCODE_DATA = 3
OPCODE_ACK = 4
OPCODE_ERROR = 5

def send_error(sock, addr, error_code, error_msg):
    """发送TFTP错误包"""
    error_packet = struct.pack("!HH", OPCODE_ERROR, error_code)
    error_packet += error_msg.encode('ascii') + b'\x00'
    sock.sendto(error_packet, addr)
    print(f"[TFTP] 发送错误: {error_code} - {error_msg}")

def handle_rrq(sock, addr, filename, mode):
    """处理读请求"""
    print(f"[TFTP] 收到读请求: {filename}, 模式: {mode}, 来自: {addr}")
    
    file_path = os.path.join(TFTP_DIR, filename)
    
    if not os.path.exists(file_path):
        print(f"[TFTP] 文件不存在: {file_path}")
        send_error(sock, addr, 1, "File not found")
        return
    
    if not os.path.isfile(file_path):
        print(f"[TFTP] 不是文件: {file_path}")
        send_error(sock, addr, 2, "Access violation")
        return
    
    try:
        file_size = os.path.getsize(file_path)
        print(f"[TFTP] 文件大小: {file_size} 字节")
        
        with open(file_path, 'rb') as f:
            block_num = 1
            total_sent = 0
            retries = 0
            
            while True:
                try:
                    # 读取数据块
                    data = f.read(BLOCK_SIZE)
                    
                    # 构建数据包
                    if data:
                        data_packet = struct.pack("!HH", OPCODE_DATA, block_num) + data
                    else:
                        # 空数据包表示文件传输完成
                        data_packet = struct.pack("!HH", OPCODE_DATA, block_num)
                    
                    # 发送数据包并等待ACK
                    while retries < MAX_RETRIES:
                        try:
                            sock.sendto(data_packet, addr)
                            progress = total_sent*100//file_size if file_size > 0 else 0
                            print(f"[TFTP] 发送块 {block_num}, 大小: {len(data)} 字节, 进度: {total_sent}/{file_size} ({progress}%)")
                            
                            # 等待ACK
                            sock.settimeout(TIMEOUT)
                            ack_packet, ack_addr = sock.recvfrom(512)
                            
                            if ack_addr != addr:
                                print(f"[TFTP] 收到来自其他地址的ACK: {ack_addr}")
                                continue
                            
                            # 解析ACK包
                            ack_opcode, ack_block = struct.unpack("!HH", ack_packet)
                            
                            if ack_opcode == OPCODE_ACK and ack_block == block_num:
                                print(f"[TFTP] 收到ACK, 块 {block_num}")
                                total_sent += len(data)
                                break
                            elif ack_opcode == OPCODE_ERROR:
                                print(f"[TFTP] 收到错误包")
                                break
                            else:
                                print(f"[TFTP] 无效的ACK包")
                                retries += 1
                                time.sleep(1)
                                
                        except socket.timeout:
                            retries += 1
                            print(f"[TFTP] 超时，重试 {retries}/{MAX_RETRIES}")
                            time.sleep(1)
                        except Exception as e:
                            print(f"[TFTP] 发送数据时出错: {e}")
                            retries += 1
                            time.sleep(1)
                    
                    if retries >= MAX_RETRIES:
                        print(f"[TFTP] 达到最大重试次数，传输失败")
                        send_error(sock, addr, 0, "Transfer timeout")
                        return
                    
                    # 如果数据为空，传输完成
                    if not data:
                        print(f"[TFTP] 文件传输完成: {filename}, 总计: {total_sent} 字节")
                        return
                    
                    block_num += 1
                    retries = 0  # 重置重试计数器
                    
                except Exception as e:
                    print(f"[TFTP] 处理数据块时出错: {e}")
                    send_error(sock, addr, 0, str(e))
                    return
                
    except Exception as e:
        print(f"[TFTP] 处理读请求时出错: {e}")
        send_error(sock, addr, 0, str(e))

def main():
    # 创建UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', TFTP_PORT))
    
    print(f"[TFTP] TFTP服务器启动")
    print(f"[TFTP] 监听端口: {TFTP_PORT}")
    print(f"[TFTP] 工作目录: {TFTP_DIR}")
    print(f"[TFTP] 块大小: {BLOCK_SIZE} 字节")
    print(f"[TFTP] 超时时间: {TIMEOUT} 秒")
    print(f"[TFTP] 最大重试次数: {MAX_RETRIES}")
    
    try:
        while True:
            # 接收请求
            sock.settimeout(None)  # 无限等待
            data, addr = sock.recvfrom(512)
            
            # 解析请求
            if len(data) < 2:
                continue
            
            opcode = struct.unpack("!H", data[:2])[0]
            
            if opcode == OPCODE_RRQ:
                # 解析读请求
                parts = data[2:].split(b'\x00')
                if len(parts) >= 2:
                    filename = parts[0].decode('ascii')
                    mode = parts[1].decode('ascii').lower()
                    handle_rrq(sock, addr, filename, mode)
            else:
                print(f"[TFTP] 不支持的操作码: {opcode}")
                
    except KeyboardInterrupt:
        print(f"[TFTP] 收到中断信号，停止服务器")
    except Exception as e:
        print(f"[TFTP] 服务器错误: {e}")
    finally:
        sock.close()
        print(f"[TFTP] TFTP服务器已停止")

if __name__ == "__main__":
    main()
