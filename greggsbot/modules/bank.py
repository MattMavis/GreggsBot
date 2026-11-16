import os

from ..state import load_json, save_json

STATE_FILE = os.path.join("state", "points.json")
START = 500
DAILY = 200
COIN = "<:SausageRoll:718927129529679945>"


class Bank:
    def __init__(self, path=STATE_FILE):
        self.path = path
        accounts = load_json(path, {})
        self.accounts = accounts if isinstance(accounts, dict) else {}

    def account(self, user_id):
        return self.accounts.setdefault(str(user_id), {"points": START, "daily": ""})

    def balance(self, user_id):
        return self.account(user_id)["points"]

    def add(self, user_id, amount):
        self.account(user_id)["points"] += amount
        save_json(self.path, self.accounts)

    def claim_daily(self, user_id, today):
        account = self.account(user_id)
        if account["daily"] == today:
            return False
        account["daily"] = today
        self.add(user_id, DAILY)
        return True

    def top(self, count):
        ranked = sorted(self.accounts.items(), key=lambda item: -item[1]["points"])
        return [(user_id, account["points"]) for user_id, account in ranked[:count]]
