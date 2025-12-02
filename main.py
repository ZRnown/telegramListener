# main.py - 主入口程序
import asyncio
import json
import logging
from modules.bot_manager import BotManager
from modules.listener import ListenerManager
from modules.data_manager import load_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 减少 Telethon 的日志输出（只显示 WARNING 及以上）
logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('telethon.network').setLevel(logging.ERROR)  # 网络层错误仍然显示
logging.getLogger('telethon.client').setLevel(logging.WARNING)  # 减少 flood wait 等 INFO 日志

async def main():
    """主函数"""
    # 读取基础配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    api_id = config['api_id']
    api_hash = config['api_hash']
    bot_token = config['bot_token']
    
    # 加载数据配置
    data = load_data()
    bot_username = data.get("bot_username")
    
    # 初始化监听管理器（暂时不传 bot_client，等机器人初始化后再设置）
    listener_manager = ListenerManager(api_id, api_hash, bot_entity=None, bot_client=None)
    
    # 初始化管理机器人
    bot_manager = BotManager(api_id, api_hash, bot_token, listener_manager)
    await bot_manager.init()
    
    # 设置机器人实体和客户端（在启动监听器之前）
    if bot_username:
        try:
            bot_entity = await bot_manager.client.get_entity(bot_username)
            listener_manager.bot_entity = bot_entity
            listener_manager.bot_client = bot_manager.client  # 传递机器人客户端给 ListenerManager
            # logger.info(f"已设置管理机器人: {bot_username}")
        except Exception as e:
            logger.warning(f"设置管理机器人失败: {e}")
    
    # 设置机器人事件处理器
    await bot_manager.setup_handlers()
    
    # 启动所有已配置的监听（此时 bot_client 已经设置）
    # logger.info("正在启动已配置的监听账号...")
    await listener_manager.reload_all()
    
    # 确保所有监听器都有 bot_client（双重保险）
    if listener_manager.bot_client:
        listener_manager.update_bot_client(listener_manager.bot_client)
    
    logger.info("🚀 系统已启动")
    
    # 获取所有监听任务（reload_all() 已经创建了任务）
    listener_tasks = list(listener_manager.tasks.values())
    
    # 并发运行管理机器人（主任务）和所有监听任务
    try:
        await asyncio.gather(
            bot_manager.run(),
            *listener_tasks,
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"运行错误: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n正在关闭系统...")
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

