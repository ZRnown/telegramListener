# modules/listener.py - 监听服务模块
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.events import NewMessage
from telethon.errors import TypeNotFoundError
import asyncio
import json
import logging
from modules.data_manager import load_data
from modules.message_handler import extract_text_from_event, build_message_link, create_event_data

logger = logging.getLogger(__name__)

class UserbotListener:
    """单个账号的监听客户端"""
    def __init__(self, session_name, account_name, api_id, api_hash, bot_entity, bot_client=None, session_string=None):
        self.session_name = session_name
        self.account_name = account_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_entity = bot_entity
        self.bot_client = bot_client  # 机器人的客户端，用于直接发送消息到目标群
        # 如果提供了 StringSession，则优先使用字符串会话；否则使用基于文件的会话
        if session_string:
            self.client = TelegramClient(StringSession(session_string), api_id, api_hash)
        else:
            self.client = TelegramClient(session_name, api_id, api_hash)
        self.listener_username = None
        self.is_running = False
    
    async def init(self):
        """初始化客户端"""
        try:
            # 先连接并检查是否已授权，避免交互式输入
            await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.client.disconnect()
                raise Exception("Session 未授权或无效")
            
            # 如果已授权，客户端已经连接并可以使用
            # 不需要调用 start()，因为 start() 在没有参数时会尝试交互式登录
            # 我们已经通过 connect() + is_user_authorized() 验证了授权状态
            
            # 获取监听账号信息
            try:
                me = await self.client.get_me()
                self.listener_username = f"@{me.username}" if getattr(me, "username", None) else "无"
                # logger.info(f"[{self.account_name}] 监听账号已初始化: {self.listener_username}")
            except Exception as e:
                self.listener_username = "未知"
                logger.error(f"[{self.account_name}] 监听账号信息获取失败: {e}")
        except Exception as e:
            # 如果启动失败（例如 session 无效），抛出异常，让调用者处理
            logger.error(f"[{self.account_name}] 客户端启动失败: {e}")
            # 确保断开连接
            try:
                await self.client.disconnect()
            except:
                pass
            raise
        
        # 不再自动发送 /start，直接开始监听
    
    async def log_incoming_event(self, event):
        """打印监听日志"""
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id)
            
            sender_name_parts = []
            if getattr(sender, "first_name", None):
                sender_name_parts.append(sender.first_name)
            if getattr(sender, "last_name", None):
                sender_name_parts.append(sender.last_name)
            sender_display_name = " ".join(sender_name_parts) if sender_name_parts else "未知"
            
            text = extract_text_from_event(event)
            snippet = text if len(text) <= 80 else text[:77] + "..."
            
            # 简化日志：只在检测到关键词时记录
            # logger.info(f"[{self.account_name}] [监听] 会话: {chat_title} | 发送者: {sender_display_name} | 文本: {snippet}")
        except Exception as e:
            logger.error(f"[{self.account_name}] [监听] 日志生成失败: {e}")
    
    async def send_keyword_alert(self, event, keyword_hit):
        """直接使用机器人客户端发送关键词提醒到目标群"""
        if not self.bot_client:
            logger.error(f"[{self.account_name}] ⚠️ 未配置机器人客户端，无法发送提醒！请检查 bot_client 是否正确设置。")
            return
        
        try:
            # 获取消息信息
            sender = await event.get_sender()
            sender_name_parts = []
            if getattr(sender, "first_name", None):
                sender_name_parts.append(sender.first_name)
            if getattr(sender, "last_name", None):
                sender_name_parts.append(sender.last_name)
            sender_display_name = " ".join(sender_name_parts) if sender_name_parts else "未知"
            sender_username = f"@{sender.username}" if getattr(sender, "username", None) else "无"
            
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or "未知"
            chat_username = getattr(chat, "username", None)  # 保存 chat username 用于构造链接
            chat_id = getattr(chat, "id", None)
            
            msg_text = extract_text_from_event(event) or "（无文本内容，可能仅为媒体消息）"
            msg_link = await build_message_link(self.client, event, chat_username, event.message.id)
            
            # 调试：记录链接构建结果
            if msg_link:
                logger.debug(f"[{self.account_name}] 消息链接: {msg_link}")
            else:
                logger.debug(f"[{self.account_name}] 无法构建消息链接 (chat_username={chat_username}, msg_id={event.message.id})")
            
            # 构造事件数据
            event_data = {
                "listener_account": self.listener_username or "未知",
                "keyword": keyword_hit,
                "sender_name": sender_display_name,
                "sender_username": sender_username,
                "chat_title": chat_title,
                "chat_id": chat_id,
                "message_id": event.message.id,
                "message_text": msg_text,
                "message_link": msg_link
            }
            
            # 使用 message_handler 模块格式化消息
            from modules.message_handler import create_keyword_alert_message
            alert_msg, buttons = create_keyword_alert_message(event_data)
            
            # 加载目标群配置
            from modules.data_manager import load_data
            data = load_data()
            target_id = data.get("target_channel_id")
            
            if not target_id:
                logger.warning(f"[{self.account_name}] ⚠️ 未设置目标群，无法发送提醒")
                return
            
            # 确保target_id是正确的格式
            if isinstance(target_id, int) and target_id > 0:
                target_id = int(f"-100{target_id}")
            
            # 直接使用机器人客户端发送消息到目标群（使用 Markdown 格式）
            await self.bot_client.send_message(
                target_id, 
                alert_msg, 
                buttons=buttons,
                parse_mode='md'  # 使用 Markdown 格式
            )
            logger.info(f"[{self.account_name}] ✅ 已发送关键词提醒: {keyword_hit} -> {target_id}")
        
        except Exception as e:
            logger.error(f"[{self.account_name}] ❌ 发送关键词提醒失败: {e}", exc_info=True)
    
    async def setup_handlers(self):
        """设置消息处理器"""
        @self.client.on(NewMessage())
        async def handler(event):
            try:
                # 不监听私聊
                if event.is_private:
                    return
                
                # 打印监听日志
                await self.log_incoming_event(event)
                
                # 加载最新配置
                data = load_data()
                keywords = data.get("keywords", [])
                
                if not keywords:
                    return
                
                text = extract_text_from_event(event)
                if not text:
                    return
                
                # 不要对自己发送的提醒再次触发
                if text.startswith("🔔 关键词提醒"):
                    return
                
                # 关键词匹配
                hit = None
                for kw in keywords:
                    if kw and kw in text:
                        hit = kw
                        break
                
                if hit:
                    # 获取聊天信息用于日志
                    try:
                        chat = await event.get_chat()
                        chat_title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id)
                    except:
                        chat_title = "未知"
                    logger.info(f"[{self.account_name}] 🔍 检测到关键词: {hit} (来源: {chat_title})")
                    await self.send_keyword_alert(event, hit)
            except TypeNotFoundError:
                # 忽略 TypeNotFoundError（Telegram API 新增类型但 Telethon 版本过旧）
                # 这是已知问题，不影响功能
                pass
            except Exception as e:
                # 其他错误记录但不中断监听
                logger.warning(f"[{self.account_name}] 消息处理错误: {e}")
                # 记录错误类型，帮助诊断
                logger.debug(f"[{self.account_name}] 错误类型: {type(e).__name__}", exc_info=True)
    
    async def start(self):
        """启动监听"""
        if self.is_running:
            return
        self.is_running = True
        await self.setup_handlers()
        logger.info(f"[{self.account_name}] 监听已启动")
    
    async def stop(self):
        """停止监听"""
        if not self.is_running:
            return
        self.is_running = False
        await self.client.disconnect()
        logger.info(f"[{self.account_name}] 监听已停止")
    
    async def run(self):
        """运行客户端（阻塞）"""
        logger.info(f"[{self.account_name}] 监听任务开始运行")
        retry_count = 0
        max_retries = 10
        
        while self.is_running:
            try:
                # 确保连接
                if not self.client.is_connected():
                    logger.info(f"[{self.account_name}] 正在连接...")
                    await self.client.connect()
                
                # 运行直到断开
                await self.client.run_until_disconnected()
                # 如果正常断开连接，退出循环
                logger.warning(f"[{self.account_name}] 连接已断开")
                break
                
            except TypeNotFoundError as e:
                # TypeNotFoundError 通常发生在消息处理时，不应该导致监听停止
                # 但如果在网络层发生，我们需要处理
                logger.debug(f"[{self.account_name}] 遇到 TypeNotFoundError: {e}")
                retry_count = 0  # 重置重试计数
                await asyncio.sleep(1)
                continue
                
            except Exception as e:
                retry_count += 1
                error_msg = str(e).lower()
                
                # 如果是连接相关错误，尝试重连
                if any(keyword in error_msg for keyword in ["disconnect", "connection", "network", "timeout"]):
                    if retry_count <= max_retries:
                        logger.warning(f"[{self.account_name}] 连接错误，尝试重连 ({retry_count}/{max_retries}): {e}")
                        await asyncio.sleep(min(retry_count * 2, 10))  # 指数退避，最多10秒
                        try:
                            if not self.client.is_connected():
                                await self.client.connect()
                            retry_count = 0  # 重连成功，重置计数
                        except Exception as reconnect_error:
                            logger.error(f"[{self.account_name}] 重连失败: {reconnect_error}")
                    else:
                        logger.error(f"[{self.account_name}] 重连次数过多，停止监听")
                        break
                else:
                    # 其他错误，记录但不停止监听
                    logger.error(f"[{self.account_name}] 监听运行错误: {e}", exc_info=True)
                    await asyncio.sleep(5)
                    retry_count = 0  # 非连接错误，重置计数
        
        logger.warning(f"[{self.account_name}] 监听任务已退出")

class ListenerManager:
    """监听管理器 - 管理所有账号的监听"""
    def __init__(self, api_id, api_hash, bot_entity, bot_client=None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_entity = bot_entity
        self.bot_client = bot_client  # 机器人的客户端，用于直接发送消息
        self.listeners = {}  # {session_name: UserbotListener}
        self.tasks = {}  # {session_name: asyncio.Task}
    
    async def start_listener(self, session_name, account_name):
        """启动一个监听客户端"""
        if session_name in self.listeners:
            logger.warning(f"监听 {session_name} 已存在")
            return False

        try:
            # 从配置中读取 session_string（如果有）
            data = load_data()
            accounts = data.get("userbot_accounts", [])
            session_string = None
            for acc in accounts:
                if acc.get("session_name") == session_name:
                    session_string = acc.get("session_string")
                    break

            listener = UserbotListener(
                session_name,
                account_name,
                self.api_id,
                self.api_hash,
                self.bot_entity,
                bot_client=self.bot_client,  # 传递机器人客户端
                session_string=session_string
            )
            
            # 记录 bot_client 状态
            if self.bot_client:
                logger.debug(f"[{account_name}] bot_client 已设置: {type(self.bot_client).__name__}")
            else:
                logger.warning(f"[{account_name}] ⚠️ bot_client 为 None，转发功能可能无法使用！")
            await listener.init()
            await listener.start()
            
            # 在后台运行
            task = asyncio.create_task(listener.run())
            self.listeners[session_name] = listener
            self.tasks[session_name] = task
            
            logger.info(f"✅ 已启动监听: {account_name} ({session_name})")
            return True
        except Exception as e:
            logger.error(f"❌ 启动监听失败 {session_name}: {e}")
            return False
    
    async def stop_listener(self, session_name):
        """停止一个监听客户端"""
        if session_name not in self.listeners:
            return False
        
        try:
            listener = self.listeners[session_name]
            await listener.stop()
            
            # 取消任务
            if session_name in self.tasks:
                self.tasks[session_name].cancel()
                try:
                    await self.tasks[session_name]
                except asyncio.CancelledError:
                    pass
                del self.tasks[session_name]
            
            del self.listeners[session_name]
            logger.info(f"✅ 已停止监听: {session_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 停止监听失败 {session_name}: {e}")
            return False
    
    async def reload_all(self):
        """重新加载所有监听（根据 data.json）"""
        data = load_data()
        accounts = data.get("userbot_accounts", [])
        
        # 停止不存在的监听
        current_sessions = {acc.get("session_name") for acc in accounts}
        for session_name in list(self.listeners.keys()):
            if session_name not in current_sessions:
                await self.stop_listener(session_name)
        
        # 启动新的监听
        for acc in accounts:
            session_name = acc.get("session_name")
            account_name = acc.get("name", session_name)
            if session_name not in self.listeners:
                await self.start_listener(session_name, account_name)
    
    def get_listener_status(self):
        """获取所有监听状态"""
        return {
            session_name: {
                "account_name": listener.account_name,
                "is_running": listener.is_running
            }
            for session_name, listener in self.listeners.items()
        }
    
    def update_bot_client(self, bot_client):
        """更新所有监听器的 bot_client"""
        self.bot_client = bot_client
        for listener in self.listeners.values():
            listener.bot_client = bot_client
        logger.info(f"✅ 已更新所有监听器的 bot_client")

