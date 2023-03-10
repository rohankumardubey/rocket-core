import os
import random
import re
import datetime
import textwrap

from collections import defaultdict
import logging
import asyncio
import time

import rctogether
from bot import Bot

logging.basicConfig(level=logging.INFO)


def parse_position(position):
    x, y = position.split(",")
    return {"x": int(x), "y": int(y)}


def position_tuple(pos):
    return (pos["x"], pos["y"])


def offset_position(position, delta):
    return {"x": position["x"] + delta["x"], "y": position["y"] + delta["y"]}


def is_adjacent(p1, p2):
    return abs(p2["x"] - p1["x"]) <= 1 and abs(p2["y"] - p1["y"]) <= 1


class Region:
    def __init__(self, top_left, bottom_right):
        self.top_left = top_left
        self.bottom_right = bottom_right

    def __contains__(self, point):
        return (
            self.top_left["x"] <= point["x"] <= self.bottom_right["x"]
            and self.top_left["y"] <= point["y"] <= self.bottom_right["y"]
        )

    def random_point(self):
        return {
            "x": random.randint(self.top_left["x"], self.bottom_right["x"]),
            "y": random.randint(self.top_left["y"], self.bottom_right["y"]),
        }

    def __repr__(self):
        return f"<Region {self.top_left!r} {self.bottom_right!r}>"


HELP_TEXT = textwrap.dedent(
    """\
        I can help you adopt a pet! Just send me a message saying 'adopt the <pet type> please'.
        The agency is just north of the main space. Drop by to see the available pets, and read more instructions on the note by the door."""
)

PETS = [
    {"emoji": "🦇", "name": "bat", "noise": "screech!"},
    {"emoji": "🐝", "name": "bee", "noise": "buzz!"},
    {"emoji": "🦕", "name": "brontosaurus", "noise": "MEEEHHH!"},
    {"emoji": "🐫", "name": "camel"},
    {"emoji": "🐈", "name": "cat", "noise": "miaow!"},
    {"emoji": "🐛", "name": "caterpillar", "noise": "munch!"},
    {"emoji": "🐄", "name": "cow", "noise": "Moo!"},
    {"emoji": "🦀", "name": "crab", "noise": "click!"},
    {"emoji": "🐊", "name": "crocodile"},
    {"emoji": "🐕", "name": "dog", "noise": "woof!"},
    {"emoji": "🐉", "name": "dragon", "noise": "🔥"},
    {"emoji": "🦅", "name": "eagle"},
    {"emoji": "🐘", "name": "elephant"},
    {"emoji": "🦩", "name": "flamingo"},
    {"emoji": "🦊", "name": "fox", "noise": "Wrahh!"},
    {"emoji": "🐸", "name": "frog", "noise": "ribbet!"},
    {"emoji": "🦒", "name": "giraffe"},
    {"emoji": "🦔", "name": "hedgehog", "noise": "scurry, scurry, scurry"},
    {"emoji": "🦛", "name": "hippo"},
    {"emoji": "👾", "name": "invader"},
    {"emoji": "🦘", "name": "kangaroo", "noise": "Chortle chortle!"},
    {"emoji": "🐨", "name": "koala", "noise": "gggrrrooowwwlll"},
    {"emoji": "🦙", "name": "llama"},
    {"emoji": "🐁", "name": "mouse", "noise": "squeak!"},
    {"emoji": "🦉", "name": "owl", "noise": "hoot hoot!"},
    {"emoji": "🦜", "name": "parrot", "noise": "HELLO!"},
    {"emoji": "🐧", "name": "penguin"},
    {"emoji": "🐖", "name": "pig", "noise": "oink!"},
    {"emoji": "🐇", "name": "rabbit"},
    {"emoji": "🚀", "name": "rocket"},
    {"emoji": "🐌", "name": "snail", "noise": "slurp!"},
    {"emoji": "🦖", "name": "t-rex", "noise": "RAWR!"},
    {"emoji": "🐅", "name": "tiger"},
    {"emoji": "🐢", "name": "turtle", "noise": "hiss!"},
    {"emoji": "🦄", "name": "unicorn", "noise": "✨"},
    {"emoji": "🪨", "name": "rock", "noise": "🤘"},
]

NOISES = {pet["emoji"]: pet.get("noise", "💖") for pet in PETS}

GENIE_NAME = os.environ.get("GENIE_NAME", "Pet Agency Genie")
GENIE_HOME = parse_position(os.environ.get("GENIE_HOME", "60,15"))
SPAWN_POINTS = {
    position_tuple(offset_position(GENIE_HOME, {"x": dx, "y": dy}))
    for (dx, dy) in [(-2, -2), (0, -2), (2, -2), (-2, 0), (2, 0), (0, 2), (2, 2)]
}

CORRAL = Region({"x": 0, "y": 40}, {"x": 19, "y": 58})

PET_BOREDOM_TIMES = (3600, 5400)
LURE_TIME_SECONDS = 600
DAY_CARE_CENTER = Region({"x": 0, "y": 62}, {"x": 11, "y": 74})

SAD_MESSAGE_TEMPLATES = [
    "Was I not a good {pet_name}?",
    "I thought you liked me.",
    "😢",
    "What will I do now?",
    "But where will I go?",
    "One day I might learn to trust again...",
    "I only wanted to make you happy.",
    "My heart hurts.",
    "Did I do something wrong?",
    "But why?",
    "💔",
]

MANNERS = [
    "please",
    "bitte",
    "le do thoil",
    "sudo",
    "per favore",
    "oh mighty djinn",
    "s'il vous plaît",
    "s'il vous plait",
    "svp",
    "por favor",
    "kudasai",
    "onegai shimasu",
    "пожалуйста",
]

THANKS_RESPONSES = ["You're welcome!", "No problem!", "❤️"]


def sad_message(pet_name):
    return random.choice(SAD_MESSAGE_TEMPLATES).format(pet_name=pet_name)


def a_an(noun):
    if noun == "unicorn":
        return "a " + noun
    if noun[0] in "AaEeIiOoUu":
        return "an " + noun
    return "a " + noun


def upfirst(text):
    return text[0].upper() + text[1:]


def response_handler(commands, pattern, include_mentions=False):
    def decorator(f):
        commands.append((pattern, f, include_mentions))
        return f

    return decorator


async def reset_agency():
    async with rctogether.RestApiSession() as session:
        for bot in await rctogether.bots.get(session):
            if bot["emoji"] == "🧞":
                pass
            elif not bot.get("message"):
                print("Bot: ", bot)
                await rctogether.bots.delete(session, bot["id"])


class Pet(Bot):
    def __init__(self, bot_json, *a, **k):
        super().__init__(bot_json, *a, **k)
        self.is_in_day_care_center = False
        if bot_json.get("message"):
            self.owner = bot_json["message"]["mentioned_entity_ids"][0]
            if "forget" in bot_json["message"]["text"]:
                self.is_in_day_care_center = True
        else:
            self.owner = None

    @property
    def type(self):
        return self.name.split(" ")[-1]

    async def queued_updates(self):
        updates = super().queued_updates()

        while True:
            next_update = asyncio.Task(updates.__anext__())
            while True:
                try:
                    update = await asyncio.wait_for(
                        asyncio.shield(next_update),
                        timeout=random.randint(*PET_BOREDOM_TIMES),
                    )
                    yield update
                    break
                except asyncio.TimeoutError:
                    if self.owner and not self.is_in_day_care_center:
                        yield CORRAL.random_point()
                except StopAsyncIteration:
                    return


class PetDirectory:
    def __init__(self):
        self._available_pets = {}
        self._owned_pets = defaultdict(list)
        self._pets_by_id = {}

    def add(self, pet):
        self._pets_by_id[pet.id] = pet

        if pet.owner:
            self._owned_pets[pet.owner].append(pet)
        else:
            self._available_pets[position_tuple(pet.pos)] = pet

    def remove(self, pet):
        del self._pets_by_id[pet.id]

        if pet.owner:
            self._owned_pets[pet.owner].remove(pet)
        else:
            del self._available_pets[position_tuple(pet.pos)]

    def available(self):
        return self._available_pets.values()

    def empty_spawn_points(self):
        return SPAWN_POINTS - set(self._available_pets.keys())

    def owned(self, owner_id):
        return self._owned_pets[owner_id]

    def __iter__(self):
        for pet in self._available_pets.values():
            yield pet

        yield from self.all_owned()

    def all_owned(self):
        for pet_collection in self._owned_pets.values():
            for pet in pet_collection:
                yield pet

    def __getitem__(self, pet_id):
        return self._pets_by_id[pet_id]

    def set_owner(self, pet, owner):
        self.remove(pet)
        pet.owner = owner["id"]
        self.add(pet)


class Agency:
    """
    public interface:
        create (static)
            (session) -> Agency
        handle_entity
            (json_blob)
    """

    commands = []

    def __init__(self, session, genie, pet_directory):
        self.session = session
        self.genie = genie
        self.pet_directory = pet_directory
        self.lured_pets_by_petter = defaultdict(list)
        self.lured_pets = {}
        self.processed_message_dt = datetime.datetime.utcnow()
        self.avatars = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    @classmethod
    async def create(cls, session):
        genie = None
        pet_directory = PetDirectory()

        for bot_json in await rctogether.bots.get(session):
            if bot_json["emoji"] == "🧞":
                genie = Bot(bot_json)
                genie.start_task(session)
                print("Found the genie: ", bot_json)
            else:
                pet = Pet(bot_json)
                pet_directory.add(pet)
                pet.start_task(session)

        if not genie:
            genie = await Bot.create(
                session,
                name=GENIE_NAME,
                emoji="🧞",
                x=GENIE_HOME["x"],
                y=GENIE_HOME["y"],
                can_be_mentioned=True,
            )

        agency = cls(session, genie, pet_directory)
        return agency

    async def close(self):
        if self.genie:
            await self.genie.close()

        for pet in self.pet_directory:
            await pet.close()

    async def spawn_pet(self, pos):
        pet = random.choice(PETS)
        while any(x.emoji == pet["emoji"] for x in self.pet_directory.available()):
            pet = random.choice(PETS)

        return await Pet.create(
            self.session,
            name=pet["name"],
            emoji=pet["emoji"],
            x=pos[0],
            y=pos[1],
        )

    def get_non_day_care_center_owned_by_type(self, pet_name, owner):
        for pet in self.pet_directory.owned(owner["id"]):
            if pet.type == pet_name and not pet.is_in_day_care_center:
                return pet
        return None

    def get_from_day_care_center_by_type(self, pet_name, owner):
        for pet in self.pet_directory.owned(owner["id"]):
            if pet.type == pet_name and pet.is_in_day_care_center:
                return pet
        return None

    def get_random_from_day_care_center(self, owner):
        pets_in_day_care = [
            pet
            for pet in self.pet_directory.owned(owner["id"])
            if pet.is_in_day_care_center
        ]
        if not pets_in_day_care:
            return None
        return random.choice(pets_in_day_care)

    def random_owned(self, owner):
        return random.choice(self.pet_directory.owned(owner["id"]))

    async def send_message(self, recipient, message_text, sender=None):
        sender = sender or self.genie
        await rctogether.messages.send(
            self.session, sender.id, f"@**{recipient['person_name']}** {message_text}"
        )

    @response_handler(commands, "time to restock")
    async def handle_restock(self, restocker, match):
        if self.pet_directory.empty_spawn_points():
            pet = min(
                self.pet_directory.available(), key=lambda pet: pet.id, default=None
            )
            if pet:
                self.pet_directory.remove(pet)
                await pet.close()
                await rctogether.bots.delete(self.session, pet.id)
                await self.send_message(
                    restocker,
                    f"{upfirst(a_an(pet.name))} was unwanted and has been sent to the farm.",
                )

        for pos in self.pet_directory.empty_spawn_points():
            pet = await self.spawn_pet(pos)
            self.pet_directory.add(pet)
        return "New pets now in stock!"

    @response_handler(commands, "adopt (a|an|the|one)? ([A-Za-z-]+)")
    async def handle_adoption(self, adopter, match):
        if not any(please in match.string.lower() for please in MANNERS):
            return "No please? Our pets are only available to polite homes."

        pet_name = match.groups()[1]

        if pet_name == "horse":
            return "Sorry, that's just a picture of a horse."

        if pet_name == "genie":
            return "You can't adopt me. I'm not a pet!"

        if pet_name == "apatosaurus":
            return "Since 2015 the brontasaurus and apatosaurus have been recognised as separate species. Would you like to adopt a brontasaurus?"

        if pet_name == "pet":
            try:
                pet = random.choice(list(self.pet_directory.available()))
            except IndexError:
                return "Sorry, we don't have any pets at the moment, perhaps it's time to restock?"
        else:
            pet = next(
                filter(
                    lambda pet: pet.name == pet_name, self.pet_directory.available()
                ),
                None,
            )

        if not pet:
            try:
                alternative = random.choice(list(self.pet_directory.available())).name
            except IndexError:
                return "Sorry, we don't have any pets at the moment, perhaps it's time to restock?"

            return f"Sorry, we don't have {a_an(pet_name)} at the moment, perhaps you'd like {a_an(alternative)} instead?"

        await self.send_message(adopter, NOISES.get(pet.emoji, "💖"), pet)
        await rctogether.bots.update(
            self.session,
            pet.id,
            {"name": f"{adopter['person_name']}'s {pet.name}"},
        )

        self.pet_directory.set_owner(pet, adopter)

        return None

    @response_handler(commands, r"(?:look after|take care of|drop off) my ([A-Za-z]+)")
    async def handle_day_care_drop_off(self, adopter, match):
        pet_name = match.groups()[0]
        pet = self.get_non_day_care_center_owned_by_type(pet_name, adopter)

        if not pet:
            try:
                suggested_alternative = self.random_owned(adopter).type
            except IndexError:
                return "Sorry, you don't have any pets to drop off, perhaps you'd like to adopt one?"
            return f"Sorry, you don't have {a_an(pet_name)}. Would you like to drop off your {suggested_alternative} instead?"

        await self.send_message(adopter, "Please don't forget about me!", pet)
        position = DAY_CARE_CENTER.random_point()
        await pet.update(position)
        pet.is_in_day_care_center = True
        return None

    @response_handler(commands, r"(?:collect|pick up|get) my ([A-Za-z]+)")
    async def handle_day_care_pick_up(self, adopter, match):
        pet_name = match.groups()[0]
        pet = self.get_from_day_care_center_by_type(pet_name, adopter)

        if not pet:
            suggested_alternative = self.get_random_from_day_care_center(adopter)
            if not suggested_alternative:
                return "Sorry, you have no pets in day care. Would you like to drop one off?"
            suggested_alternative = suggested_alternative.name.split(" ")[-1]
            return f"Sorry, you don't have {a_an(pet_name)} to collect. Would you like to collect your {suggested_alternative} instead?"

        await self.send_message(adopter, NOISES.get(pet.emoji, "💖"), pet)
        pet.is_in_day_care_center = False

    @response_handler(commands, "thank")
    async def handle_thanks(self, adopter, match):
        return random.choice(THANKS_RESPONSES)

    @response_handler(commands, r"abandon my ([A-Za-z-]+)")
    async def handle_abandonment(self, adopter, match):
        pet_name = match.groups()[0]
        pet = next(
            (
                pet
                for pet in self.pet_directory.owned(adopter["id"])
                if pet.type == pet_name
            ),
            None,
        )

        if not pet:
            try:
                suggested_alternative = self.random_owned(adopter).type
            except IndexError:
                return "Sorry, you don't have any pets to abandon, perhaps you'd like to adopt one?"
            return f"Sorry, you don't have {a_an(pet_name)}. Would you like to abandon your {suggested_alternative} instead?"

        self.pet_directory.remove(pet)

        # There may be unhandled updates in the pet's message queue - they don't matter because the exceptions will just be logged.
        # To be more correct we could push a delete event through the pet's queue.
        await pet.close()
        await self.send_message(adopter, sad_message(pet_name), pet)
        await rctogether.bots.delete(self.session, pet.id)
        return None

    @response_handler(
        commands, r"well[- ]actually|feigning surprise|backseat driving|subtle[- ]*ism"
    )
    async def handle_social_rules(self, adopter, match):
        return "Oh, you're right. Sorry!"

    @response_handler(commands, r"pet the ([A-Za-z-]+)")
    async def handle_pet_a_pet(self, petter, match):
        # For the moment this command needs to be addressed to the genie (maybe won't later).
        # Find any pets next to the speaker of the right type.
        #  Do we have any pets of the right type next to the speaker?

        pet_type = match.group(1)

        for pet in self.pet_directory.all_owned():
            if is_adjacent(petter["pos"], pet.pos) and pet.type == pet_type:
                self.lured_pets[pet.id] = time.time() + LURE_TIME_SECONDS
                self.lured_pets_by_petter[petter["id"]].append(pet)

    @response_handler(commands, r"give my ([A-Za-z]+) to", include_mentions=True)
    async def handle_give_pet(self, giver, match, mentioned_entities):
        pet_name = match.group(1)
        pet = next(
            (
                pet
                for pet in self.pet_directory.owned(giver["id"])
                if pet.type == pet_name
            ),
            None,
        )

        if not pet:
            try:
                suggested_alternative = self.random_owned(giver).type
            except IndexError:
                return "Sorry, you don't have any pets to give away, perhaps you'd like to adopt one?"
            return f"Sorry, you don't have {a_an(pet_name)}. Would you like to give your {suggested_alternative} instead?"

        if not mentioned_entities:
            return f"Who to you want to give your {pet_name} to?"
        recipient = self.avatars.get(mentioned_entities[0])

        if not recipient:
            return "Sorry, I don't know who that is! (Are they online?)"

        await self.send_message(recipient, NOISES.get(pet.emoji, "💖"), pet)
        await rctogether.bots.update(
            self.session,
            pet.id,
            {"name": f"{recipient['person_name']}'s {pet.name}"},
        )

        self.pet_directory.set_owner(pet, recipient)
        position = offset_position(recipient["pos"], random.choice(DELTAS))
        await pet.update(position)
        return

    @response_handler(commands, r"help")
    async def handle_help(self, adopter, match):
        return HELP_TEXT

    async def handle_mention(self, adopter, message, mentioned_entity_ids):
        for (pattern, handler, include_mentions) in self.commands:
            match = re.search(pattern, message["text"], re.IGNORECASE)
            if match:
                if include_mentions:
                    response = await handler(
                        self,
                        adopter,
                        match,
                        [x for x in mentioned_entity_ids if x != self.genie.id],
                    )
                else:
                    response = await handler(self, adopter, match)
                if response:
                    await self.send_message(adopter, response)
                return

        await self.send_message(
            adopter, "Sorry, I don't understand. Would you like to adopt a pet?"
        )

    async def handle_entity(self, entity):
        if entity["type"] == "Avatar":
            self.avatars[entity["id"]] = entity

            message = entity.get("message")

            if message and self.genie.id in message["mentioned_entity_ids"]:
                message_dt = datetime.datetime.strptime(
                    message["sent_at"], "%Y-%m-%dT%H:%M:%SZ"
                )
                if message_dt > self.processed_message_dt:
                    await self.handle_mention(
                        entity, message, message["mentioned_entity_ids"]
                    )
                    self.processed_message_dt = message_dt

        if entity["type"] == "Avatar":
            for pet in self.lured_pets_by_petter.get(entity["id"], []):
                position = offset_position(entity["pos"], random.choice(DELTAS))
                await pet.update(position)

            for pet in self.pet_directory.owned(entity["id"]):
                if pet.is_in_day_care_center:
                    continue
                if pet.id in self.lured_pets:
                    if self.lured_pets[pet.id] < time.time():  # if timer is expired
                        del self.lured_pets[pet.id]
                        for petter_id in self.lured_pets_by_petter:
                            for lured_pet in self.lured_pets_by_petter[petter_id]:
                                if lured_pet.id == pet.id:
                                    self.lured_pets_by_petter[petter_id].remove(
                                        lured_pet
                                    )
                    else:
                        continue
                position = offset_position(entity["pos"], random.choice(DELTAS))
                await pet.update(position)

        if entity["type"] == "Bot":
            try:
                pet = self.pet_directory[entity["id"]]
            except KeyError:
                pass
            else:
                pet.pos = entity["pos"]


DELTAS = [{"x": x, "y": y} for x in [-1, 0, 1] for y in [-1, 0, 1] if x != 0 or y != 0]


async def main():
    async with rctogether.RestApiSession() as session:
        agency = await Agency.create(session)

        async for entity in rctogether.WebsocketSubscription():
            await agency.handle_entity(entity)


if __name__ == "__main__":
    asyncio.run(main())
