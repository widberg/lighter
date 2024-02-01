import os

import asyncio
from dotenv import load_dotenv
from homeassistant_api import Client
from twitchAPI import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.types import AuthScope, ChatEvent, CustomRewardRedemptionStatus
from twitchAPI.eventsub import EventSub
from twitchAPI.chat import Chat, EventData, ChatMessage
from webcolors import (
    HTML5SimpleColor,
    html5_parse_simple_color,
    name_to_rgb,
)

load_dotenv(".env")

HOMEASSISTANT_URL = os.getenv("HOMEASSISTANT_URL")
HOMEASSISTANT_TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
HOMEASSISTANT_LIGHT_DOMAIN = os.getenv("HOMEASSISTANT_LIGHT_DOMAIN")
HOMEASSISTANT_LIGHT_ENTITY = os.getenv("HOMEASSISTANT_LIGHT_ENTITY")

APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")
REWARD_ID = os.getenv("REWARD_ID")
USER_SCOPE = [
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.CHANNEL_MANAGE_REDEMPTIONS,
]
EVENTSUB_URL = "https://localhost:8080/eventsub"

ALLOW_CHANNEL_POINTS = os.getenv("ALLOW_CHANNEL_POINTS").lower() in ("true", "1", "t")
ALLOW_CHAT = os.getenv("ALLOW_CHAT").lower() in ("true", "1", "t")
TRANSITION_LENGTH = float(os.getenv("TRANSITION_LENGTH"))

PATTERNS = {
    "trans": [
        [91, 206, 250],
        [245, 169, 184],
        [255, 255, 255],
    ],
}

twitch = None
chat = None
light = None
loop = None


def get_color_from_string(string: str) -> HTML5SimpleColor:
    string = string.lower()
    try:
        return html5_parse_simple_color(string)
    except Exception:
        try:
            return HTML5SimpleColor(*name_to_rgb(string))
        except Exception:
            return None


def get_color_from_input(input: str) -> HTML5SimpleColor:
    input_split = input.split()
    input = "".join(input_split)
    if color := get_color_from_string(input):
        return color

    for word in input_split:
        if color := get_color_from_string(word):
            return color

    input_hash = hash(input)
    return HTML5SimpleColor(
        input_hash & 0xFF, (input_hash >> 8) & 0xFF, (input_hash >> 16) & 0xFF
    )


def turn_on_light(color: HTML5SimpleColor, transition=TRANSITION_LENGTH):
    rgb_color = [color.red, color.green, color.blue]
    brightness = sum(rgb_color) / 3
    light.turn_on(
        entity_id=HOMEASSISTANT_LIGHT_ENTITY,
        transition=transition,
        rgb_color=rgb_color,
        brightness=brightness,
    )


async def on_redemption(data: dict):
    event = data.get("event")
    id = event.get("id")
    user_input = event.get("user_input")
    try:
        simple_color = get_color_from_input(user_input)
        await loop.run_in_executor(None, lambda: turn_on_light(simple_color))
        await twitch.update_redemption_status(
            TARGET_CHANNEL, REWARD_ID, id, CustomRewardRedemptionStatus.FULFILLED
        )
    except Exception:
        return


async def on_ready(ready_event: EventData):
    print("Bot is ready for work, joining channels")
    await ready_event.chat.join_room(TARGET_CHANNEL)


async def on_message(message_event: ChatMessage):
    try:
        simple_color = get_color_from_input(message_event.text)
        await loop.run_in_executor(None, lambda: turn_on_light(simple_color))
    except Exception:
        return


async def run():
    global light, loop
    homeassistant = Client(api_url=HOMEASSISTANT_URL, token=HOMEASSISTANT_TOKEN)
    light = homeassistant.get_domain(HOMEASSISTANT_LIGHT_DOMAIN)
    loop = asyncio.get_event_loop()

    global twitch, chat
    twitch = await Twitch(APP_ID, APP_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    event_sub = EventSub(EVENTSUB_URL, APP_ID, 8080, twitch)
    if ALLOW_CHANNEL_POINTS:
        await event_sub.listen_channel_points_custom_reward_redemption_add(
            TARGET_CHANNEL, on_redemption, reward_id=REWARD_ID
        )
    event_sub.start()

    chat = await Chat(twitch)
    chat.register_event(ChatEvent.READY, on_ready)
    if ALLOW_CHAT:
        chat.register_event(ChatEvent.MESSAGE, on_message)
    chat.start()

    try:
        input("press ENTER to stop\n")
    finally:
        await event_sub.stop()
        chat.stop()
        await twitch.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
