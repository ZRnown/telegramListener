# modules/message_handler.py - 消息处理模块
import json
import re
import logging
from telethon import Button, utils

logger = logging.getLogger(__name__)

def extract_text_from_event(event):
    """获取消息的纯文本内容"""
    return (event.raw_text or "").strip()


async def build_message_link(client, event, chat_username, message_id):
    """
    生成消息链接：
    1. 优先尝试官方 API (export_message_link)
    2. 失败则尝试手动拼接公开用户名链接
    3. 再失败则强制拼接私有频道链接 (t.me/c/xxx/xxx)
    """
    chat_id = event.chat_id

    # 尝试 1: 官方 API (最准确，但私有群+开启防复制时会失效)
    try:
        # 显式传入 input_chat 和 message_id
        link = await client.export_message_link(event.input_chat, message_id)
        if link:
            if link.startswith('http:'):
                link = link.replace('http:', 'https:', 1)
            return link
    except Exception:
        # 失败则继续后续逻辑
        pass

    # 尝试 2: 如果有公开用户名 (Public Channel/Group)
    if chat_username:
        return f"https://t.me/{chat_username}/{message_id}"

    # 尝试 3: 强制手动拼接私有链接 (Private Channel/Group)
    # 私有频道/群组 ID 通常以 -100 开头 (如 -1003270297333)
    # 链接格式需要去掉 -100，变成 https://t.me/c/3270297333/173

    # 使用 Telethon 的工具函数获取 peer id
    real_id = utils.get_peer_id(event.input_chat)
    str_id = str(real_id)

    final_internal_id = None

    # 情况 A: -100 开头的 ID
    if str_id.startswith('-100'):
        final_internal_id = str_id[4:]
    # 情况 B: 100 开头的正数 ID（某些内部表示）
    elif str_id.startswith('100') and len(str_id) > 10:
        final_internal_id = str_id[3:]
    # 情况 C: 其他负数 ID，尝试取绝对值
    elif str_id.startswith('-'):
        final_internal_id = str_id[1:]

    # 兜底：还是没有就用 chat_id 的绝对值
    if not final_internal_id:
        final_internal_id = str(abs(chat_id))
        if final_internal_id.startswith("100"):
            final_internal_id = final_internal_id[3:]

    manual_link = f"https://t.me/c/{final_internal_id}/{message_id}"

    # 这里可以根据需要增加对话题（Forum Topics）的处理
    # 例如: https://t.me/c/xxxx/topic_id/message_id

    return manual_link

def create_keyword_alert_message(event_data):
    """构造关键词提醒消息（带 Markdown 格式）"""
    listener = event_data.get("listener_account", "未知")
    keyword = event_data.get("keyword", "未知")
    sender_name = event_data.get("sender_name", "未知")
    sender_username = event_data.get("sender_username", "无")
    chat_title = event_data.get("chat_title", "未知")
    msg_text = event_data.get("message_text", "（无文本内容）")
    msg_link = event_data.get("message_link")
    
    # 格式化用户名显示：如果是"无"或空，显示"无"；否则显示用户名
    if sender_username == "无" or not sender_username or sender_username.strip() == "":
        username_display = "无"
    else:
        username_display = sender_username
    
    # 使用 Markdown 格式，关键信息加粗
    alert_msg = (
        f"🔔 **关键词提醒**\n\n"
        f"📱 **监听账号**： `{listener}`\n"
        f"🔑 **关键字**： `{keyword}`\n"
        f"👤 **发送者**： {sender_name}\n"
        f"📝 **用户名**： {username_display}\n"
        f"💬 **来源群组**： {chat_title}\n"
        f"📄 **消息内容**：\n```\n{msg_text}\n```"
    )
    
    # 必须添加"查看消息"按钮，优先使用消息链接（格式：https://t.me/username/message_id 或 https://t.me/c/...）
    final_link = None
    
    # 1. 优先使用 build_message_link 得到的消息链接
    if msg_link and msg_link.strip():
        final_link = msg_link.strip()
        logger.debug(f"[keyword_alert] 初始 message_link: {final_link}")
        # 确保是 HTTPS 格式
        if final_link.startswith('http://'):
            final_link = final_link.replace('http://', 'https://', 1)
    # 2. 如果没有链接，尝试从消息文本中提取 https://t.me/username/message_id 或 https://t.me/c/... 格式的链接
    if not final_link:
        link_match = re.search(r'(https://t\.me/[^\s\)/]+/[^\s\)]+)', msg_text)
        if link_match:
            final_link = link_match.group(1)
            # 验证格式
            if final_link.count('/') < 3:
                logger.debug(f"[keyword_alert] 从消息文本提取的链接无效: {final_link}")
                final_link = None

    # 3. 按钮必须显示（用户要求）
    if final_link and final_link.startswith('https://t.me/'):
        logger.info(f"[keyword_alert] 最终使用链接生成按钮: {final_link}")
        buttons = [[Button.url("查看消息", final_link)]]
    else:
        # 如果完全没有链接，不显示按钮（避免跳转到错误页面）
        logger.info(f"[keyword_alert] 无法生成有效链接，按钮将不显示。原始 msg_link={msg_link!r}, chat_title={chat_title!r}")
        buttons = None
    
    return alert_msg, buttons

def create_event_data(listener_account, keyword, sender_name, sender_username, 
                      chat_title, message_text, message_link):
    """创建事件数据（JSON格式）"""
    return {
        "type": "keyword_alert",
        "listener_account": listener_account,
        "keyword": keyword,
        "sender_name": sender_name,
        "sender_username": sender_username,
        "chat_title": chat_title,
        "message_text": message_text,
        "message_link": message_link
    }

