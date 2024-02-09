from typing import List, Tuple

import numpy as np
import verbs


class LiquidationAgent:
    def __init__(
        self,
        env,
        i: int,
        morpho_blue_abi: type,
        mintable_erc20_abi: type,
        oracle_abi: type,
        morpho_blue_snippets_abi: type,
        morpho_blue_address: bytes,
        morpho_blue_snippets_address: bytes,
        oracle_address: bytes,
        token_a_address: bytes,
        token_b_address: bytes,
        irm_address: bytes,
        lltv: int,
        borrow_address: List[bytes],
    ):

        self.address = verbs.utils.int_to_address(i)
        env.create_account(self.address, int(1e30))

        self.morpho_blue_abi = morpho_blue_abi
        self.oracle_abi = oracle_abi
        self.morpho_blue_address = morpho_blue_address
        self.oracle_address = oracle_address
        self.irm_address = irm_address
        self.lltv = lltv
        self.morpho_blue_snippets_abi = morpho_blue_snippets_abi
        self.morpho_blue_snippets_address = morpho_blue_snippets_address
        self.mintable_erc20_abi = mintable_erc20_abi

        # collateral token - risky asset
        self.token_a_address = token_a_address
        # debt token - stablecoin
        self.token_b_address = token_b_address

        # market params
        self.market_params = (
            self.token_b_address,
            self.token_a_address,
            self.oracle_address,
            self.irm_address,
            self.lltv,
        )
        self.id_market = self.morpho_blue_snippets_abi.getId.call(
            env, self.address, morpho_blue_snippets_address, [self.market_params]
        )[0][
            0
        ]  # bytes

        # tokens data
        self.decimals_token_a = mintable_erc20_abi.decimals.call(
            env, self.address, self.token_a_address, []
        )[0][0]
        self.decimals_token_b = mintable_erc20_abi.decimals.call(
            env, self.address, self.token_b_address, []
        )[0][0]

        self.borrow_address = borrow_address
        self.step = 0

    def update(self, rng: np.random.Generator, env) -> List:

        borrowers_data = []
        for borrower in self.borrow_address:
            health_factor = (
                self.morpho_blue_snippets_abi.userHealthFactor.call(
                    env,
                    self.address,
                    self.morpho_blue_snippets_address,
                    [self.market_params, self.id_market, borrower],
                )[0][0]
                / 10**18
            )
            borrowers_data.append((borrower, health_factor))

        # filter risky positions
        risky_positions = filter(lambda x: x[1] < 0.98, borrowers_data)

        # TODO: do accountability to check whether it is profitable to liquidate
        # taking into account slippage of Uniswap
        # Adapt from https://github.com/simtopia/verbs-examples/blob/main/agents/liquidation_agent.py

        # create transaction
        tx = []
        for borrower, health_factor in risky_positions:
            _debt_shares, collateral_assets = self.morpho_blue_abi.position.call(
                env, self.address, self.morpho_blue_address, [self.id_market, borrower]
            )[0][1:]
            print(f"health factor: {health_factor}")

            tx.append(
                self.morpho_blue_abi.liquidate.transaction(
                    self.address,
                    self.morpho_blue_address,
                    [self.market_params, borrower, collateral_assets // 2, 0, b""],
                )
            )

        self.step += 1
        return tx

    def record(self, env) -> Tuple[float, float]:

        balance_debt_asset = (
            self.mintable_erc20_abi.balanceOf.call(
                env, self.address, self.token_b_address, [self.address]
            )[0][0]
            / 10**self.decimals_token_b
        )

        balance_collateral_asset = (
            self.mintable_erc20_abi.balanceOf.call(
                env, self.address, self.token_a_address, [self.address]
            )[0][0]
            / 10**self.decimals_token_a
        )

        return balance_debt_asset, balance_collateral_asset
