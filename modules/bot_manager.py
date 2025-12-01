# modules/bot_manager.py - 管理机器人模块
from telethon import TelegramClient, events, Button
import asyncio
import json
import logging
import os
import base64
from modules.data_manager import (
    load_data, save_data, add_account, remove_account,
    add_keywords, remove_keyword, set_target_channel, set_bot_username
)
from modules.message_handler import create_keyword_alert_message

logger = logging.getLogger(__name__)

class BotManager:
    """管理机器人"""
    def __init__(self, api_id, api_hash, bot_token, listener_manager):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.listener_manager = listener_manager
        self.client = TelegramClient('bot_session', api_id, api_hash)
        self.waiting_for = {}  # {user_id: "account_name" | "keyword" | "target" | "bot" | "session"}
    
    async def init(self):
        """初始化机器人"""
        # 如果使用 bot_token，删除旧的 session 文件，强制使用 token 登录
        session_path = 'bot_session.session'
        if os.path.exists(session_path):
            logger.info(f"删除旧的 bot session 文件: {session_path}")
            try:
                os.remove(session_path)
            except Exception as e:
                logger.warning(f"删除 session 文件失败: {e}")
        
        # 重新创建 client（因为 session 文件已删除）
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        
        await self.client.start(bot_token=self.bot_token)
        # 自动设置 bot_username
        me = await self.client.get_me()
        bot_username = f"@{me.username}" if me.username else None
        logger.info(f"机器人信息: ID={me.id}, Username={bot_username}")
        
        if bot_username:
            data = load_data()
            if "bot_username" not in data or not data.get("bot_username"):
                set_bot_username(bot_username)
            
            # 更新 listener_manager 的 bot_entity（无论是否已设置都要更新，确保使用正确的机器人）
            try:
                bot_entity = await self.client.get_entity(bot_username)
                self.listener_manager.bot_entity = bot_entity
                logger.info(f"✅ 已设置管理机器人实体: {bot_username} (ID: {bot_entity.id})")
            except Exception as e:
                logger.error(f"❌ 设置管理机器人实体失败: {e}")
        else:
            logger.warning("⚠️ 机器人没有用户名，无法设置 bot_entity")
        
        # logger.info(f"管理机器人已初始化: {bot_username}")
    
    def get_main_keyboard(self):
        """主菜单键盘（回复键盘）"""
        return [
            [Button.text("📱 账号管理"), Button.text("🔑 关键词管理")],
            [Button.text("🎯 设置目标群"), Button.text("📋 查看配置")],
        ]
    
    def get_account_menu(self):
        """账号管理内联菜单（只包含操作按钮，不包含账号列表按钮）"""
        return [
            [Button.inline("➕ 添加账号", b"account_add")],
            [Button.inline("➖ 移除账号", b"account_remove")],
            [Button.inline("🔙 返回主菜单", b"menu_main")]
        ]
    
    def get_keyword_menu(self):
        """关键词管理内联菜单"""
        return [
            [Button.inline("➕ 添加关键词", b"keyword_add")],
            [Button.inline("➖ 删除关键词", b"keyword_remove")],
            [Button.inline("📋 查看关键词列表", b"keyword_list")],
            [Button.inline("🔙 返回主菜单", b"menu_main")]
        ]
    
    async def save_session_from_file(self, event, session_name):
        """从文件保存 session
        
        返回:
            (success: bool, msg: str)
        """
        try:
            # 下载文件
            file_path = await event.download_media(file=f"{session_name}.session")
            # 如果下载成功，文件已经保存
            if os.path.exists(file_path):
                # 重命名到项目目录
                target_path = os.path.join(os.getcwd(), f"{session_name}.session")
                if file_path != target_path:
                    os.rename(file_path, target_path)
                return True, "Session 文件已保存"
        except Exception as e:
            return False, f"保存文件失败: {e}"
        return False, "未找到文件"
    
    async def save_session_from_string(self, session_string, session_name):
        """从字符串保存 session 字符串（用于 StringSession，不再落地为 sqlite 文件）
        
        返回:
            (success: bool, msg: str, cleaned_session: str | None)
        """
        try:
            cleaned = session_string.strip()
            if not cleaned:
                return False, "Session 字符串为空", None
            # 这里不强制校验 base64，交由 Telethon 在使用时校验
            return True, "Session 字符串已接收", cleaned
        except Exception as e:
            return False, f"处理 session 字符串失败: {e}", None
    
    async def setup_handlers(self):
        """设置事件处理器"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "🤖 **关键词监听管理机器人**\n\n"
                "请选择功能：",
                buttons=self.get_main_keyboard()
            )
        
        @self.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def message_handler(event):
            text = event.raw_text or ""
            user_id = event.sender_id
            
            # 优先处理来自 Userbot 的事件数据（JSON格式）
            # 注意：JSON 消息不应该被当作普通消息处理，也不应该回复给用户
            if text.startswith('{') and text.endswith('}'):
                try:
                    event_data = json.loads(text)
                    if "type" in event_data and event_data["type"] == "keyword_alert":
                        alert_msg, buttons = create_keyword_alert_message(event_data)
                        data_obj = load_data()
                        target_id = data_obj.get("target_channel_id")
                        
                        if target_id:
                            try:
                                # 确保target_id是正确的格式
                                if isinstance(target_id, int) and target_id > 0:
                                    target_id = int(f"-100{target_id}")
                                
                                await self.client.send_message(target_id, alert_msg, buttons=buttons, parse_mode='md')
                                return
                            except Exception as e:
                                logger.error(f"发送到目标群失败: {e}")
                                return
                        else:
                            logger.warning("未设置目标群")
                            return
                except (json.JSONDecodeError, KeyError):
                    pass  # 不是有效的JSON事件数据，继续处理普通消息
                except Exception as e:
                    logger.error(f"处理JSON事件数据失败: {e}")
                    return
            
            # 处理等待状态
            if user_id in self.waiting_for:
                wait_type = self.waiting_for[user_id]
                
                if wait_type == "session":
                    # 用户发送了 session，需要从 session 中获取账号信息
                    session_name = f"anon_{len(load_data().get('userbot_accounts', [])) + 1}"
                    session_str = None
                    account_name = "未知账号"
                    success = False
                    msg = ""
                    
                    # 检查是否是文件
                    if event.message.media:
                        success, msg = await self.save_session_from_file(event, session_name)
                        if success:
                            # 从文件 session 中获取账号信息
                            try:
                                from telethon import TelegramClient
                                temp_client = TelegramClient(session_name, self.api_id, self.api_hash)
                                await temp_client.connect()
                                if await temp_client.is_user_authorized():
                                    me = await temp_client.get_me()
                                    account_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (f"@{me.username}" if me.username else f"用户{me.id}")
                                await temp_client.disconnect()
                            except Exception as e:
                                logger.warning(f"从 session 文件获取账号信息失败: {e}")
                                account_name = f"账号_{session_name}"
                    else:
                        # 当作字符串处理
                        result = await self.save_session_from_string(text, session_name)
                        if isinstance(result, tuple) and len(result) == 3:
                            success, msg, session_str = result
                        else:
                            # 兼容旧版本返回格式
                            success, msg = result[:2]
                            session_str = result[2] if len(result) > 2 else text.strip()
                        
                        if success and session_str:
                            # 从 StringSession 中获取账号信息
                            try:
                                from telethon import TelegramClient
                                from telethon.sessions import StringSession
                                temp_client = TelegramClient(StringSession(session_str), self.api_id, self.api_hash)
                                await temp_client.connect()
                                if await temp_client.is_user_authorized():
                                    me = await temp_client.get_me()
                                    account_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or (f"@{me.username}" if me.username else f"用户{me.id}")
                                await temp_client.disconnect()
                            except Exception as e:
                                logger.warning(f"从 session 字符串获取账号信息失败: {e}")
                                account_name = f"账号_{session_name}"
                    
                    if success:
                        # 添加账号记录
                        add_success, add_msg = add_account(account_name, session_name, session_str)
                        if add_success:
                            # 立即尝试启动监听
                            data = load_data()
                            bot_username = data.get("bot_username")
                            if bot_username and not self.listener_manager.bot_entity:
                                try:
                                    bot_entity = await self.client.get_entity(bot_username)
                                    self.listener_manager.bot_entity = bot_entity
                                except Exception as e:
                                    logger.warning(f"获取管理机器人实体失败: {e}")
                            
                            start_ok = await self.listener_manager.start_listener(session_name, account_name)
                            listener = self.listener_manager.listeners.get(session_name)
                            listener_user = getattr(listener, "listener_username", "未知") if listener else "未知"
                            running = listener.is_running if listener else False

                            if start_ok and running:
                                status_text = "已启动"
                                prefix = "✅ 账号添加并启动成功！"
                            else:
                                status_text = (
                                    "启动失败：session 文件可能无效（例如出现 'file is not a database' 错误）。"
                                    " 请确认这是 Telethon 生成的 `.session` 文件，"
                                    "或使用 `login_anon.py` 登录生成后再重试。"
                                )
                                prefix = "⚠️ 账号已保存，但监听启动失败"

                            await event.respond(
                                f"{prefix}\n\n"
                                f"账号名称：**{account_name}**\n"
                                f"监听账号：{listener_user}\n"
                                f"监听状态：{status_text}"
                            )
                        else:
                            await event.respond(f"❌ 添加账号失败：{add_msg}")
                    else:
                        await event.respond(f"❌ {msg}")
                    
                    del self.waiting_for[user_id]
                    return
                
                elif wait_type == "keyword":
                    new_keywords = [kw.strip() for kw in text.split('\n') if kw.strip()]
                    added = add_keywords(new_keywords)
                    if added:
                        await event.respond(f"✅ 已添加关键词：{', '.join(added)}")
                    else:
                        await event.respond("⚠️ 这些关键词已存在。")
                    del self.waiting_for[user_id]
                    return
                
                elif wait_type == "target":
                    try:
                        target_id = None
                        if text.startswith('-100') or text.startswith('-'):
                            target_id = int(text)
                        else:
                            entity = await self.client.get_entity(text)
                            target_id = entity.id
                        
                        set_target_channel(target_id)
                        await event.respond(f"✅ 已设置目标群：`{target_id}`")
                    except Exception as e:
                        await event.respond(f"❌ 设置失败：{e}\n\n请确保发送的是有效的频道/群 ID 或用户名。")
                    del self.waiting_for[user_id]
                    return
                
            # 处理主菜单键盘按钮
            if text == "📱 账号管理":
                data_obj = load_data()
                accounts = data_obj.get("userbot_accounts", [])
                status = self.listener_manager.get_listener_status()
                
                if accounts:
                    msg = "📱 **账号管理**\n\n**当前账号列表：**\n\n"
                    for i, acc in enumerate(accounts, 1):
                        session_name = acc.get("session_name", "未知")
                        status_info = status.get(session_name, {})
                        running = "✅ 运行中" if status_info.get("is_running") else "❌ 未运行"
                        msg += f"{i}. **{acc.get('name', '未知')}** {running}\n"
                else:
                    msg = "📱 **账号管理**\n\n当前没有已添加的账号。"
                
                await event.respond(
                    msg,
                    buttons=self.get_account_menu()
                )
            
            elif text == "🔑 关键词管理":
                data_obj = load_data()
                keywords = data_obj.get("keywords", [])
                
                if keywords:
                    msg = "🔑 **关键词管理**\n\n**当前关键词列表：**\n\n"
                    for i, kw in enumerate(keywords, 1):
                        msg += f"{i}. `{kw}`\n"
                else:
                    msg = "🔑 **关键词管理**\n\n当前没有已添加的关键词。"
                
                await event.respond(
                    msg,
                    buttons=self.get_keyword_menu()
                )
            
            elif text == "🎯 设置目标群":
                self.waiting_for[user_id] = "target"
                await event.respond(
                    "🎯 **设置目标群**\n\n"
                    "请发送目标频道/群的 ID（例如：`-1001234567890`）或用户名（例如：`@channel`）：\n\n"
                    "💡 提示：\n"
                    "- 频道/群 ID 可以通过 @userinfobot 获取\n"
                    "- 确保机器人已加入目标频道/群并具有发送消息权限"
                )
            
            elif text == "📋 查看配置":
                data_obj = load_data()
                accounts = data_obj.get("userbot_accounts", [])
                keywords = data_obj.get("keywords", [])
                target = data_obj.get("target_channel_id")
                status = self.listener_manager.get_listener_status()
                
                # 获取目标群名称
                target_name = "未设置"
                if target:
                    try:
                        target_entity = await self.client.get_entity(target)
                        target_name = getattr(target_entity, "title", None) or getattr(target_entity, "username", None) or str(target)
                    except:
                        target_name = str(target)
                
                msg = "📋 **当前配置**\n\n"
                msg += f"📱 **账号数量**：{len(accounts)} (运行中: {sum(1 for s in status.values() if s.get('is_running'))})\n"
                if keywords:
                    msg += f"🔑 **关键词**：{', '.join([f'`{kw}`' for kw in keywords])}\n"
                else:
                    msg += f"🔑 **关键词**：无\n"
                msg += f"🎯 **目标群**：{target_name}\n\n"
                
                if accounts:
                    msg += "**账号列表：**\n"
                    for acc in accounts:
                        session_name = acc.get("session_name", "未知")
                        status_info = status.get(session_name, {})
                        running = "✅" if status_info.get("is_running") else "❌"
                        msg += f"- {running} {acc.get('name', '未知')} (`{session_name}`)\n"
                    msg += "\n"
                
                if keywords:
                    msg += "**关键词列表：**\n"
                    for kw in keywords:
                        msg += f"- `{kw}`\n"
                
                await event.respond(msg)
            
            elif text == "🔙 返回主菜单":
                await event.respond(
                    "🤖 **关键词监听管理机器人**\n\n"
                    "请选择功能：",
                    buttons=self.get_main_keyboard()
                )
                if user_id in self.waiting_for:
                    del self.waiting_for[user_id]
        
        # 处理内联按钮回调
        @self.client.on(events.CallbackQuery)
        async def callback_handler(event):
            data = event.data.decode('utf-8')
            user_id = event.sender_id
            
            try:
                if data == "menu_main":
                    await event.edit(
                        "🤖 **关键词监听管理机器人**\n\n"
                        "请选择功能：",
                        buttons=self.get_main_keyboard()
                    )
                
                elif data == "account_add":
                    self.waiting_for[user_id] = "session"
                    await event.respond(
                        "➕ **添加账号**\n\n"
                        "请直接发送 session 文件或 session 字符串：\n\n"
                        "💡 提示：\n"
                        "- 可以发送 `.session` 文件\n"
                        "- 也可以发送 session 字符串（StringSession）"
                    )
                    await event.answer()
                
                elif data == "account_remove":
                    data_obj = load_data()
                    accounts = data_obj.get("userbot_accounts", [])
                    if not accounts:
                        await event.respond("❌ 当前没有已添加的账号。")
                        await event.answer()
                        return
                    
                    buttons = []
                    for acc in accounts:
                        buttons.append([Button.inline(
                            f"❌ {acc.get('name', '未知')} ({acc.get('session_name', '未知')})",
                            f"account_del_{acc.get('session_name', '')}"
                        )])
                    buttons.append([Button.inline("🔙 返回", b"menu_accounts")])
                    
                    await event.edit("选择要移除的账号：", buttons=buttons)
                
                elif data.startswith("account_del_"):
                    session_name = data.replace("account_del_", "")
                    success = remove_account(session_name)
                    if success:
                        await self.listener_manager.stop_listener(session_name)
                        await event.respond(f"✅ 已移除账号：{session_name}\n监听已停止")
                    else:
                        await event.respond(f"❌ 移除失败")
                    data_obj = load_data()
                    accounts = data_obj.get("userbot_accounts", [])
                    status = self.listener_manager.get_listener_status()
                    data_obj = load_data()
                    accounts = data_obj.get("userbot_accounts", [])
                    status = self.listener_manager.get_listener_status()
                    
                    if accounts:
                        msg = "📱 **账号管理**\n\n**当前账号列表：**\n\n"
                        for i, acc in enumerate(accounts, 1):
                            session_name = acc.get("session_name", "未知")
                            status_info = status.get(session_name, {})
                            running = "✅ 运行中" if status_info.get("is_running") else "❌ 未运行"
                            msg += f"{i}. **{acc.get('name', '未知')}** {running}\n"
                    else:
                        msg = "📱 **账号管理**\n\n当前没有已添加的账号。"
                    
                    await event.edit(msg, buttons=self.get_account_menu())
                
                elif data == "menu_accounts":
                    data_obj = load_data()
                    accounts = data_obj.get("userbot_accounts", [])
                    status = self.listener_manager.get_listener_status()
                    
                    if accounts:
                        msg = "📱 **账号管理**\n\n**当前账号列表：**\n\n"
                        for i, acc in enumerate(accounts, 1):
                            session_name = acc.get("session_name", "未知")
                            status_info = status.get(session_name, {})
                            running = "✅ 运行中" if status_info.get("is_running") else "❌ 未运行"
                            msg += f"{i}. **{acc.get('name', '未知')}** {running}\n"
                            msg += f"   Session: `{session_name}`\n\n"
                    else:
                        msg = "📱 **账号管理**\n\n当前没有已添加的账号。"
                    
                    await event.edit(
                        msg,
                        buttons=self.get_account_menu()
                    )
                
                elif data == "keyword_add":
                    self.waiting_for[user_id] = "keyword"
                    await event.respond(
                        "➕ **添加关键词**\n\n"
                        "请直接发送要添加的关键词（一行一个，或一次发送多个用换行分隔）："
                    )
                    await event.answer()
                
                elif data == "keyword_remove":
                    data_obj = load_data()
                    keywords = data_obj.get("keywords", [])
                    if not keywords:
                        await event.respond("❌ 当前没有已添加的关键词。")
                        await event.answer()
                        return
                    
                    buttons = []
                    for kw in keywords:
                        buttons.append([Button.inline(
                            f"❌ {kw}",
                            f"keyword_del_{kw}"
                        )])
                    buttons.append([Button.inline("🔙 返回", b"menu_keywords")])
                    
                    await event.edit("选择要删除的关键词：", buttons=buttons)
                
                elif data.startswith("keyword_del_"):
                    keyword = data.replace("keyword_del_", "")
                    success = remove_keyword(keyword)
                    if success:
                        await event.respond(f"✅ 已删除关键词：{keyword}")
                    else:
                        await event.respond(f"❌ 删除失败：关键词不存在")
                    await event.edit("🔑 **关键词管理**", buttons=self.get_keyword_menu())
                
                elif data == "keyword_list":
                    data_obj = load_data()
                    keywords = data_obj.get("keywords", [])
                    if not keywords:
                        await event.respond("📋 当前没有已添加的关键词。")
                    else:
                        msg = "📋 **关键词列表**\n\n"
                        for i, kw in enumerate(keywords, 1):
                            msg += f"{i}. `{kw}`\n"
                        await event.respond(msg)
                    await event.edit("🔑 **关键词管理**", buttons=self.get_keyword_menu())
                
                elif data == "menu_keywords":
                    await event.edit(
                        "🔑 **关键词管理**\n\n"
                        "管理监听关键词：",
                        buttons=self.get_keyword_menu()
                    )
                
            except Exception as e:
                logger.error(f"回调处理失败: {e}")
                await event.respond(f"❌ 操作失败：{e}")
                await event.answer()
        
    
    async def run(self):
        """运行机器人"""
        await self.client.run_until_disconnected()
