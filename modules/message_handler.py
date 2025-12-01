# modules/message_handler.py - 消息处理模块
import json
import re
from telethon import Button

def extract_text_from_event(event):
    """获取消息的纯文本内容"""
    return (event.raw_text or "").strip()

async def build_message_link(client, event, chat_username=None, message_id=None):
    """构造消息链接（返回 https://t.me/username/message_id 格式）"""
    try:
        # 1) 优先使用 export_message_link（返回格式：https://t.me/username/message_id）
        try:
            link = await client.export_message_link(event.message)
            if link:
                # export_message_link 返回的格式通常是 https://t.me/username/message_id
                # 确保是 HTTPS 格式
                if link.startswith('http://'):
                    link = link.replace('http://', 'https://', 1)
                elif not link.startswith('https://'):
                    # 如果返回的不是完整 URL，尝试构造
                    if link.startswith('t.me/'):
                        link = f"https://{link}"
                    elif '/' in link:
                        # 可能是 username/message_id 格式
                        link = f"https://t.me/{link}"
                    else:
                        # 只有用户名，无法构造完整链接
                        return None
                # 验证链接格式：https://t.me/username/message_id
                # 链接应该类似：https://t.me/username/123 或 https://t.me/c/chat_id/message_id
                if link.startswith('https://t.me/'):
                    # 检查是否有 message_id（链接中至少要有2个部分：username 和 message_id）
                    parts = link.replace('https://t.me/', '').split('/')
                    if len(parts) >= 2 and parts[1].isdigit():
                        return link
        except Exception as e:
            # export_message_link 可能失败（例如受保护的聊天、私聊等）
            pass
        
        # 2) 如果 export_message_link 失败，尝试手动构造链接
        try:
            if not chat_username:
                chat = await event.get_chat()
                chat_username = getattr(chat, 'username', None)
            
            if not message_id:
                message_id = event.message.id
            
            if chat_username and message_id:
                # 构造链接：https://t.me/username/message_id
                link = f"https://t.me/{chat_username}/{message_id}"
                return link
        except Exception:
            pass
        
        # 3) 从消息文本中提取 https://t.me/ 格式的链接
        text = extract_text_from_event(event)
        if text:
            # 匹配 https://t.me/username/message_id 格式（必须包含至少一个斜杠）
            m = re.search(r'(https://t\.me/[^\s\)/]+/[^\s\)]+)', text)
            if m:
                link = m.group(1)
                # 验证链接格式
                if link.count('/') >= 3:
                    return link
        
        return None
    except Exception as e:
        return None

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
    
    # 必须添加"查看消息"按钮，优先使用消息链接（格式：https://t.me/username/message_id）
    final_link = None
    
    # 1. 优先使用消息链接（应该是 https://t.me/username/message_id 格式）
    if msg_link and msg_link.strip():
        final_link = msg_link.strip()
        # 确保是 HTTPS 格式
        if final_link.startswith('http://'):
            final_link = final_link.replace('http://', 'https://', 1)
        # 验证格式：必须是 https://t.me/username/message_id（必须包含至少3个斜杠）
        if not final_link.startswith('https://t.me/'):
            # 如果不是正确格式，尝试修复
            if final_link.startswith('t.me/'):
                final_link = f"https://{final_link}"
            elif '/' in final_link and not final_link.startswith('http'):
                final_link = f"https://t.me/{final_link}"
        
        # 验证链接格式：https://t.me/username/message_id（必须包含至少3个斜杠）
        if final_link.count('/') < 3:
            final_link = None  # 格式不正确，忽略
    
    # 2. 如果没有链接，尝试从消息文本中提取 https://t.me/username/message_id 格式的链接
    if not final_link:
        link_match = re.search(r'(https://t\.me/[^\s\)/]+/[^\s\)]+)', msg_text)
        if link_match:
            final_link = link_match.group(1)
            # 验证格式
            if final_link.count('/') < 3:
                final_link = None
    
    # 3. 如果还是没有有效链接，尝试从 chat_title 中提取用户名构造频道链接
    # 注意：无法获取 message_id 时，只能链接到频道/群，不能链接到具体消息
    if not final_link:
        # 尝试从 chat_title 中提取用户名（如果包含 @ 或看起来像用户名）
        if '@' in chat_title:
            username_match = re.search(r'@?([a-zA-Z0-9_]+)', chat_title)
            if username_match:
                final_link = f"https://t.me/{username_match.group(1)}"
        # 如果 chat_title 本身看起来像用户名（不包含空格，只包含字母数字下划线）
        elif re.match(r'^[a-zA-Z0-9_]+$', chat_title):
            final_link = f"https://t.me/{chat_title}"
    
    # 4. 按钮必须显示（用户要求）
    # 如果有有效链接（包含 message_id），使用完整链接；否则使用频道链接
    if final_link and final_link.startswith('https://t.me/'):
        buttons = [[Button.url("查看消息", final_link)]]
    else:
        # 如果完全没有链接，不显示按钮（避免跳转到错误页面）
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

