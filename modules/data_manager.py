# modules/data_manager.py - 数据管理模块
import json
import os

DATA_FILE = 'data.json'

def load_data():
    """加载动态配置数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "userbot_accounts": [],
        "keywords": [],
        "target_channel_id": None,
        "bot_username": None
    }

def save_data(data):
    """保存动态配置数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def add_account(name, session_name, session_string=None):
    """添加账号
    session_string:
        - 若为 None，表示使用本地 .session 文件
        - 若为字符串，表示使用 Telethon StringSession
    """
    data = load_data()
    accounts = data.get("userbot_accounts", [])
    # 检查是否已存在
    if any(acc.get("session_name") == session_name for acc in accounts):
        return False, "账号已存在"
    accounts.append({
        "name": name,
        "session_name": session_name,
        "session_string": session_string
    })
    data["userbot_accounts"] = accounts
    save_data(data)
    return True, "添加成功"

def remove_account(session_name):
    """移除账号"""
    data = load_data()
    accounts = data.get("userbot_accounts", [])
    original_count = len(accounts)
    data["userbot_accounts"] = [a for a in accounts if a.get("session_name") != session_name]
    save_data(data)
    return len(data["userbot_accounts"]) < original_count

def add_keywords(new_keywords):
    """添加关键词"""
    data = load_data()
    keywords = data.get("keywords", [])
    added = []
    for kw in new_keywords:
        if kw not in keywords:
            keywords.append(kw)
            added.append(kw)
    data["keywords"] = keywords
    save_data(data)
    return added

def remove_keyword(keyword):
    """删除关键词"""
    data = load_data()
    keywords = data.get("keywords", [])
    if keyword in keywords:
        keywords.remove(keyword)
        data["keywords"] = keywords
        save_data(data)
        return True
    return False

def set_target_channel(channel_id):
    """设置目标频道"""
    data = load_data()
    data["target_channel_id"] = channel_id
    save_data(data)

def set_bot_username(username):
    """设置机器人用户名"""
    data = load_data()
    data["bot_username"] = username
    save_data(data)

