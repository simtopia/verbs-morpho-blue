import verbs
from verbs.sim import BaseAgent


class SupplyAgent(BaseAgent):
    def __init__(self, env, i: int, eth: int):

        address = verbs.utils.int_to_address(i)
        self.deploy(env, address, eth)

    def update(self, *args):
        pass

    def record(self, *args):
        pass
