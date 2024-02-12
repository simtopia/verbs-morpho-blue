from typing import List, Tuple

import eth_abi
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
        uniswap_pool_abi: type,
        quoter_abi: type,
        swap_router_abi: type,
        uniswap_pool_address: bytes,
        quoter_address: bytes,
        swap_router_address: bytes,
        uniswap_fee: int,
        hf_threshold: float,
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

        # Uniswap variables
        self.uniswap_pool_abi = uniswap_pool_abi
        self.uniswap_pool_address = uniswap_pool_address
        self.quoter_abi = quoter_abi
        self.quoter_address = quoter_address
        self.swap_router_abi = swap_router_abi
        self.swap_router_address = swap_router_address
        self.uniswap_fee = uniswap_fee

        # balance of token a and token b
        self.balance_collateral_asset = []
        self.balance_debt_asset = []

        # HF threshold to look for liquidations
        self.hf_threshold = hf_threshold

    def accountability(
        self,
        env,
        liquidation_address: bytes,
    ) -> bool:
        """
        Makes the accountability of a liquidation and returns a bool indicating
        whether a liquidation is profitable or not
        """
        _debt_shares, collateral_assets = self.morpho_blue_abi.position.call(
            env,
            self.address,
            self.morpho_blue_address,
            [self.id_market, liquidation_address],
        )[0][1:]
        seized_assets = collateral_assets // 2
        liquidation_call_event = self.morpho_blue_abi.liquidate.call(
            env,
            self.address,
            self.morpho_blue_address,
            [self.market_params, liquidation_address, seized_assets, 0, b""],
        )[1]
        try:
            decoded_liquidation_call_event = self.morpho_blue_abi.Liquidate.decode(
                liquidation_call_event[2][1]
            )  # Liquidate event is the third event emitted
        except eth_abi.exceptions.InsufficientDataBytes:
            # The liquidation did not go through because the position was actually healthy
            # Morpho Blue Snippets sometimes returns a Health Factor that does not
            # correspond to the output of the function `_is_Healthy`
            # in https://github.com/morpho-org/morpho-blue/blob/129f8f9c0f65bc797fab93a6ba8e7046ca4490d3/src/Morpho.sol#L527
            return False
        debt_to_cover = decoded_liquidation_call_event[0]
        liquidated_collateral_amount = decoded_liquidation_call_event[2]

        quote = self.quoter_abi.quoteExactOutputSingle.call(
            env,
            self.address,
            self.quoter_address,
            [
                (
                    self.token_a_address,
                    self.token_b_address,
                    debt_to_cover,
                    self.uniswap_fee,
                    0,
                )
            ],
        )[0]
        amount_collateral_from_swap = quote[0]

        return amount_collateral_from_swap < liquidated_collateral_amount

    def update(self, rng: np.random.Generator, env) -> List:

        current_balance_collateral_asset = self.mintable_erc20_abi.balanceOf.call(
            env,
            self.address,
            self.token_a_address,
            [
                self.address,
            ],
        )[0][0]
        current_balance_debt_asset = self.mintable_erc20_abi.balanceOf.call(
            env,
            self.address,
            self.token_b_address,
            [
                self.address,
            ],
        )[0][0]

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
        risky_positions = filter(lambda x: x[1] < self.hf_threshold, borrowers_data)

        # filter those positions for which liquidating is profitable
        liquidatable_positions = filter(
            lambda x: self.accountability(
                env,
                x[0],
            ),
            risky_positions,
        )

        # create transaction
        tx = []
        for borrower, health_factor in liquidatable_positions:
            _debt_shares, collateral_assets = self.morpho_blue_abi.position.call(
                env, self.address, self.morpho_blue_address, [self.id_market, borrower]
            )[0][1:]

            tx.append(
                self.morpho_blue_abi.liquidate.transaction(
                    self.address,
                    self.morpho_blue_address,
                    [self.market_params, borrower, collateral_assets // 2, 0, b""],
                    checked=False,  # sim does not crash if revert
                )
            )

        if self.step > 0:
            # check if liquidator has open short position in the debt asset
            if self.balance_debt_asset[-1] > current_balance_debt_asset:
                debt = self.balance_debt_asset[-1] - current_balance_debt_asset
                swap_tx = self.swap_router_abi.exactOutputSingle.transaction(
                    self.address,
                    self.swap_router_address,
                    [
                        (
                            self.token_a_address,
                            self.token_b_address,
                            self.uniswap_fee,
                            self.address,
                            10**32,
                            debt,
                            current_balance_collateral_asset,
                            0,
                        )
                    ],
                )
                tx.append(swap_tx)

        # update balances
        self.balance_collateral_asset.append(current_balance_collateral_asset)
        self.balance_debt_asset.append(current_balance_debt_asset)

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
