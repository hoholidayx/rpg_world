"""Deterministic mock payloads for the Play WebUI scaffold."""

from __future__ import annotations

from collections.abc import Iterable


MOCK_SESSIONS: list[dict[str, str]] = [
    {
        "id": "demo_session",
        "title": "雾港序章",
        "summary": "码头钟楼下的第一幕，适合验证 Play WebUI 基础流程。",
    },
    {
        "id": "market_shadow",
        "title": "黑市边缘",
        "summary": "用于检查多会话卡片、场景切换和历史加载。",
    },
]

MOCK_HISTORY: dict[str, list[dict[str, str]]] = {
    "demo_session": [
        {
            "role": "user",
            "content": "我拉紧斗篷，沿着潮湿的石阶走向码头钟楼。",
        },
        {
            "role": "assistant",
            "content": "雾气贴着地面翻涌，钟楼二层透出一线琥珀色灯光。守夜人停下擦拭灯罩的动作，像是已经等你很久。",
        },
        {
            "role": "user",
            "content": "我压低声音问他：今晚是谁敲响了第十三下钟？",
        },
        {
            "role": "assistant",
            "content": "守夜人没有立刻回答。他从怀里取出一枚沾着盐霜的铜钥匙，轻轻推到你面前：\"先确认你还记得门后的名字。\"",
        },
    ],
    "market_shadow": [
        {
            "role": "user",
            "content": "我穿过挂满红灯的棚廊，寻找售卖旧地图的摊主。",
        },
        {
            "role": "assistant",
            "content": "摊主戴着银色面具，摊面上只有三样东西：一张空白羊皮纸、一支断羽笔，以及一枚还在跳动的骰子。",
        },
    ],
}

MOCK_SCENES: dict[str, dict[str, object]] = {
    "demo_session": {
        "attrs": {"天气": "海雾", "危险": "低", "线索": "铜钥匙"},
        "time": "雨夜 23:40",
        "location": "雾港钟楼码头",
        "presentCharacters": ["你", "守夜人伊凡", "远处的敲钟者"],
        "mood": "潮湿、压抑、带着未说出口的秘密",
    },
    "market_shadow": {
        "attrs": {"天气": "无风", "危险": "中", "线索": "跳动的骰子"},
        "time": "午夜前一刻",
        "location": "红棚黑市",
        "presentCharacters": ["你", "银面摊主", "巡街傀儡"],
        "mood": "拥挤、低声交易、每个影子都像在偷听",
    },
}

MOCK_COMMANDS: list[dict[str, str]] = [
    {"name": "/continue", "description": "推进当前剧情", "mode": "slash"},
    {"name": "/scene", "description": "查看或刷新当前场景", "mode": "slash"},
    {"name": "/ooc", "description": "以玩家身份补充偏好或限制", "mode": "ooc"},
    {"name": "/roll 1d20", "description": "进行一次演示骰点", "mode": "slash"},
]


def mock_session_ids() -> list[str]:
    return [item["id"] for item in MOCK_SESSIONS]


def mock_session_title(session_id: str) -> str:
    for item in MOCK_SESSIONS:
        if item["id"] == session_id:
            return item["title"]
    return session_id


def mock_session_summary(session_id: str) -> str:
    for item in MOCK_SESSIONS:
        if item["id"] == session_id:
            return item["summary"]
    return "Play API mock session"


def mock_history(session_id: str) -> list[dict[str, str]]:
    return list(MOCK_HISTORY.get(session_id, MOCK_HISTORY["demo_session"]))


def mock_scene(session_id: str) -> dict[str, object]:
    return dict(MOCK_SCENES.get(session_id, MOCK_SCENES["demo_session"]))


def normalize_sessions(items: Iterable[object]) -> list[str]:
    sessions = [str(item) for item in items if str(item)]
    return sessions or mock_session_ids()
