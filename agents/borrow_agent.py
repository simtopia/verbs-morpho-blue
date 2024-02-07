from typing import Tuple

import numpy as np
import verbs


class BorrowAgent:
    def __init__(
        self,
        env,
        i: int,
        morpho_blue_abi,
        mintable_erc20_abi,
        oracle_abi,
        morpho_blue_snippets_abi,
        morpho_blue_address: bytes,
        morpho_blue_snippets_address: bytes,
        token_a_address: bytes,  # collateral asset
        token_b_address: bytes,  # debt asset
        oracle_address: bytes,
        irm_address: bytes,
        lltv: int,
        activation_rate: float,
        initial_ltv: float,
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
        self.initial_ltv = initial_ltv  # * self.lltv
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

        self.decimals_token_a = mintable_erc20_abi.decimals.call(
            env, self.address, self.token_a_address, []
        )[0][0]
        self.decimals_token_b = mintable_erc20_abi.decimals.call(
            env, self.address, self.token_b_address, []
        )[0][0]

        self.has_borrowed = False
        self.has_supplied = False

        assert (
            0 < activation_rate and activation_rate < 1
        ), "activation_rate has to be between 0 and 1"
        self.activation_rate = activation_rate

        self.step = 0

    def update(self, rng: np.random.Generator, env):
        self.step += 1
        tx = []
        collateral_amount = 10
        if rng.random() < self.activation_rate:
            if not self.has_supplied:
                supply_tx = self.morpho_blue_abi.supplyCollateral.transaction(
                    self.address,
                    self.morpho_blue_address,
                    [
                        self.market_params,
                        collateral_amount
                        * 10**self.decimals_token_a,  # supply 100 tokens of
                        self.address,
                        b"",
                    ],
                )
                self.has_supplied = True
                tx.append(supply_tx)
            elif not self.has_borrowed:
                # borrow
                price_collateral = (
                    self.oracle_abi.price.call(
                        env,
                        self.address,
                        self.oracle_address,
                        [],
                    )[0][0]
                    / 10**36
                )  # MB oracle returns the price with 36 decimals
                u = rng.uniform(low=0.9, high=1.0)
                borrow_amount = (
                    u * price_collateral * collateral_amount * self.initial_ltv
                )
                borrow_tx = self.morpho_blue_abi.borrow.transaction(
                    self.address,
                    self.morpho_blue_address,
                    [
                        self.market_params,
                        int(borrow_amount * 10**self.decimals_token_b),
                        0,
                        self.address,
                        self.address,
                    ],
                )
                self.has_borrowed = True
                tx.append(borrow_tx)
        return tx

    def record(self, env) -> Tuple[int, float, float, float, float]:
        """Record the state of the agent"""
        health_factor = (
            self.morpho_blue_snippets_abi.userHealthFactor.call(
                env,
                self.address,
                self.morpho_blue_snippets_address,
                [self.market_params, self.id_market, self.address],
            )[0][0]
            / 10**18
        )
        debt_assets = (
            self.morpho_blue_snippets_abi.borrowAssetsUser.call(
                env,
                self.address,
                self.morpho_blue_snippets_address,
                [self.market_params, self.address],
            )[0][0]
            / 10**self.decimals_token_b
        )
        collateral_assets = (
            self.morpho_blue_snippets_abi.collateralAssetsUser.call(
                env,
                self.address,
                self.morpho_blue_snippets_address,
                [self.id_market, self.address],
            )[0][0]
            / 10**self.decimals_token_a
        )
        price_collateral = (
            self.oracle_abi.price.call(env, self.address, self.oracle_address, [],)[
                0
            ][0]
            / 10**36
        )  # MB oracle returns the price with 36 decimals

        return (
            self.step,
            health_factor,
            debt_assets,
            collateral_assets,
            price_collateral,
        )
