import argparse
import json

import verbs

from agents import ZERO_ADDRESS
from agents.borrow_agent import BorrowAgent
from agents.liquidation_agent import LiquidationAgent
from agents.supply_agent import SupplyAgent
from agents.uniswap_agent import UniswapAgent
from utils.mint_approve import mint_and_approve_dai, mint_and_approve_weth
from utils.plot import plot_results_borrowers

MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"
OWNER = "0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa"

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
DAI = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
DAI_ADMIN = "0x9759A6Ac90977b93B58547b4A71c78317f391A28"

UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
UNISWAP_WETH_DAI = "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8"
SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
UNISWAP_QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"


def run_sim(
    key: str,
    block_number: int,
    seed: int,
    lltv: int,
    sigma: float,
    n_steps: int,
    n_borrow_agents: int,
):
    fee = 3000

    # ABIs
    dai_abi = verbs.abi.load_abi("abi/dai.abi")
    weth_erc20_abi = verbs.abi.load_abi("abi/WETHMintableERC20.abi")

    morpho_blue_abi = verbs.abi.load_abi("abi/MorphoBlue.abi")
    uniswap_aggregator_abi = verbs.abi.load_abi("abi/UniswapAggregator.abi")
    morpho_blue_snippets_abi = verbs.abi.load_abi("abi/MorphoBlueSnippets.abi")

    swap_router_abi = verbs.abi.load_abi("abi/SwapRouter.abi")
    uniswap_pool_abi = verbs.abi.load_abi("abi/UniswapV3Pool.abi")
    quoter_abi = verbs.abi.load_abi("abi/Quoter_v2.abi")

    # convert addresses to bytes
    weth_address = verbs.utils.hex_to_bytes(WETH)
    dai_address = verbs.utils.hex_to_bytes(DAI)
    dai_admin_address = verbs.utils.hex_to_bytes(DAI_ADMIN)
    morpho_blue_address = verbs.utils.hex_to_bytes(MORPHO_BLUE)
    adaptive_curve_irm_address = verbs.utils.hex_to_bytes(ADAPTIVE_CURVE_IRM)
    owner_address = verbs.utils.hex_to_bytes(OWNER)
    swap_router_address = verbs.utils.hex_to_bytes(SWAP_ROUTER)
    uniswap_weth_dai_address = verbs.utils.hex_to_bytes(UNISWAP_WETH_DAI)
    quoter_address = verbs.utils.hex_to_bytes(UNISWAP_QUOTER)

    # Fork mainenv
    env = verbs.envs.ForkEnv(
        "https://eth-mainnet.g.alchemy.com/v2/{}".format(key),
        0,
        block_number,
    )

    # --------------------------------------------------
    # Morpho Blue
    # 1. Create Uniswap oracle
    # 2. Approve the LLTV
    # 3. Create a new market with ETH/DAI/LLTV/Oracle
    # 4. Supply liquidity to the market
    # -------------------------------------------------

    owner = morpho_blue_abi.owner.call(env, ZERO_ADDRESS, morpho_blue_address, [])[0][0]
    assert owner == OWNER.lower()

    # We load the Uniswap Aggregator contract that gets the price from the Uniswap pool
    with open("abi/UniswapAggregator.json", "r") as f:
        uniswap_aggregator_contract = json.load(f)

    uniswap_aggregator_address = uniswap_aggregator_abi.constructor.deploy(
        env,
        owner_address,
        uniswap_aggregator_contract["bytecode"],
        [
            uniswap_weth_dai_address,
            weth_address,
            dai_address,
        ],
    )

    is_lltv_enabled = morpho_blue_abi.isLltvEnabled.call(
        env, verbs.utils.hex_to_bytes(owner), morpho_blue_address, [lltv]
    )[0][0]
    if not is_lltv_enabled:
        morpho_blue_abi.enableLltv.execute(
            sender=owner_address, address=morpho_blue_address, env=env, args=[lltv]
        )

    is_irm_enabled = morpho_blue_abi.isIrmEnabled.call(
        env, owner_address, morpho_blue_address, [adaptive_curve_irm_address]
    )
    assert is_irm_enabled, "IRM has to be enabled"

    # Create market
    market_params = (
        dai_address,
        weth_address,
        uniswap_aggregator_address,
        adaptive_curve_irm_address,
        lltv,
    )

    morpho_blue_abi.createMarket.execute(
        sender=verbs.utils.hex_to_bytes(owner),
        address=morpho_blue_address,
        env=env,
        args=[market_params],
    )

    # ------------------------
    # Liquidity provider agent
    # -----------------------
    supplier_agent = SupplyAgent(env, i=1, eth=10**30)

    # mint and approve tokens for the supplier agent
    # - Mint DAI and WETH
    # - Approve the Swap Router to use these in their transactions
    mint_and_approve_weth(
        env=env,
        weth_abi=weth_erc20_abi,
        weth_address=weth_address,
        recipient=supplier_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(1e24),
    )

    mint_and_approve_dai(
        env=env,
        dai_abi=dai_abi,
        dai_address=dai_address,
        dai_admin_address=dai_admin_address,
        recipient=supplier_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(1e30),
    )

    # supplier supplies some DAI
    morpho_blue_abi.supply.execute(
        sender=supplier_agent.address,
        address=morpho_blue_address,
        env=env,
        args=[
            market_params,
            10**25,
            0,
            supplier_agent.address,
            b"",
        ],
    )

    # ---------------------------------
    # Morpho Blue snippets https://github.com/morpho-org/morpho-blue-snippets/tree/main
    # Contract with usefuf functions such as `userHealthFactor`
    # ---------------------------------
    with open("abi/MorphoBlueSnippets.json", "r") as f:
        morpho_blue_snippets_contract = json.load(f)

    morpho_blue_snippets_address = morpho_blue_snippets_abi.constructor.deploy(
        env,
        ZERO_ADDRESS,
        morpho_blue_snippets_contract["bytecode"],
        [
            morpho_blue_address,
        ],
    )

    # ----------------
    # Borrower
    # ----------------
    borrow_agent = []
    for i in range(n_borrow_agents):
        borrow_agent.append(
            BorrowAgent(
                env=env,
                i=100 + i,
                morpho_blue_abi=morpho_blue_abi,
                morpho_blue_snippets_abi=morpho_blue_snippets_abi,
                morpho_blue_address=morpho_blue_address,
                morpho_blue_snippets_address=morpho_blue_snippets_address,
                mintable_erc20_abi=weth_erc20_abi,
                oracle_abi=uniswap_aggregator_abi,
                token_a_address=weth_address,
                token_b_address=dai_address,
                oracle_address=uniswap_aggregator_address,
                irm_address=adaptive_curve_irm_address,
                lltv=lltv,
                activation_rate=0.8,
                initial_ltv=0.75,
            )
        )
    for i in range(n_borrow_agents):
        mint_and_approve_weth(
            env=env,
            weth_abi=weth_erc20_abi,
            weth_address=weth_address,
            contract_approved_address=morpho_blue_address,
            recipient=borrow_agent[i].address,
            amount=int(1e24),
        )

    # ----------------
    # Liquidation agent
    # ----------------
    liquidation_agent = LiquidationAgent(
        env=env,
        i=1000,
        morpho_blue_abi=morpho_blue_abi,
        mintable_erc20_abi=weth_erc20_abi,
        oracle_abi=uniswap_aggregator_abi,
        morpho_blue_snippets_abi=morpho_blue_snippets_abi,
        morpho_blue_address=morpho_blue_address,
        morpho_blue_snippets_address=morpho_blue_snippets_address,
        oracle_address=uniswap_aggregator_address,
        token_a_address=weth_address,
        token_b_address=dai_address,
        irm_address=adaptive_curve_irm_address,
        lltv=lltv,
        borrow_address=[agent.address for agent in borrow_agent],
        quoter_address=quoter_address,
        quoter_abi=quoter_abi,
        swap_router_abi=swap_router_abi,
        swap_router_address=swap_router_address,
        uniswap_fee=fee,
        uniswap_pool_abi=uniswap_pool_abi,
        uniswap_pool_address=uniswap_weth_dai_address,
        hf_threshold=0.99,
    )

    # mint and approve tokens for the liquidator agent
    # - Mint DAI and WETH
    # - Approve Morpho Blue and Swap router to use their tokens
    mint_and_approve_dai(
        env=env,
        dai_abi=dai_abi,
        dai_address=dai_address,
        contract_approved_address=morpho_blue_address,
        dai_admin_address=dai_admin_address,
        recipient=liquidation_agent.address,
        amount=int(5e29),
    )
    mint_and_approve_weth(
        env=env,
        weth_abi=weth_erc20_abi,
        weth_address=weth_address,
        recipient=liquidation_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(5e29),
    )

    mint_and_approve_dai(
        env=env,
        dai_abi=dai_abi,
        dai_address=dai_address,
        contract_approved_address=swap_router_address,
        dai_admin_address=dai_admin_address,
        recipient=liquidation_agent.address,
        amount=int(5e29),
    )

    mint_and_approve_weth(
        env=env,
        weth_abi=weth_erc20_abi,
        weth_address=weth_address,
        recipient=liquidation_agent.address,
        contract_approved_address=swap_router_address,
        amount=int(5e29),
    )

    # ---------------
    # Uniswap agent
    # ---------------
    uniswap_agent = UniswapAgent(
        env=env,
        dt=0.01,
        fee=fee,
        i=10,
        mu=0.0,
        sigma=sigma,
        swap_router_abi=swap_router_abi,
        swap_router_address=swap_router_address,
        token_a_address=weth_address,
        token_b_address=dai_address,
        uniswap_pool_abi=uniswap_pool_abi,
        uniswap_pool_address=uniswap_weth_dai_address,
    )

    # mint and approve tokens for the Uniswap agent
    # - Mint DAI and WETH
    # - Approve the Swap Router to use these in their transactions
    mint_and_approve_weth(
        env=env,
        weth_abi=weth_erc20_abi,
        weth_address=weth_address,
        recipient=uniswap_agent.address,
        contract_approved_address=swap_router_address,
        amount=int(1e24),
    )
    mint_and_approve_dai(
        env=env,
        dai_abi=dai_abi,
        dai_address=dai_address,
        contract_approved_address=swap_router_address,
        dai_admin_address=dai_admin_address,
        recipient=uniswap_agent.address,
        amount=int(1e30),
    )

    # -------------
    # Run sim
    # -------------
    agents = [uniswap_agent] + borrow_agent + [liquidation_agent]
    runner = verbs.sim.Sim(seed, env, agents)
    results = runner.run(n_steps=n_steps)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("key", type=str, help="Alchemy key")
    parser.add_argument(
        "--block", type=int, default=19163600, help="Ethereum block number"
    )
    parser.add_argument("--sigma", type=float, default=0.2, help="price volatility")
    parser.add_argument(
        "--n_steps", type=int, default=100, help="Number of steps of the simulation"
    )
    parser.add_argument(
        "--n_borrow_agents", type=int, default=2, help="Number of borrowing agents"
    )

    args = parser.parse_args()

    key = args.key
    block_number = args.block
    n_steps = args.n_steps
    sigma = args.sigma
    n_borrow_agents = args.n_borrow_agents

    # run simulation
    lltv = 9 * 10**17
    results = run_sim(
        key=key,
        block_number=block_number,
        seed=10,
        lltv=lltv,
        sigma=sigma,
        n_steps=n_steps,
        n_borrow_agents=n_borrow_agents,
    )
    records_borrow_agents = [x[1 : (1 + n_borrow_agents)] for x in results]
    plot_results_borrowers(
        dirname="results", records=records_borrow_agents, lltv=lltv / 10**18
    )
