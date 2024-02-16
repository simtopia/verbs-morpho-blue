import json
from functools import partial
from pathlib import Path

import verbs
from verbs.utils import ZERO_ADDRESS

from simulations import abi
from simulations.agents.borrow_agent import BorrowAgent
from simulations.agents.liquidation_agent import LiquidationAgent
from simulations.agents.supply_agent import SupplyAgent
from simulations.agents.uniswap_agent import DummyUniswapAgent, UniswapAgent
from simulations.utils.erc20 import mint_and_approve_dai, mint_and_approve_weth

PATH = Path(__file__).parent

MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"
OWNER = "0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa"

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
DAI = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
DAI_ADMIN = "0x9759A6Ac90977b93B58547b4A71c78317f391A28"

UNISWAP_WETH_DAI = "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8"
SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
UNISWAP_QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"


def runner(
    env,
    seed: int,
    n_steps: int,
    n_borrow_agents: int,
    sigma: float,
    lltv: int,
    init_cache: bool = False,
):

    # Convert addresses to bytes
    weth_address = verbs.utils.hex_to_bytes(WETH)
    dai_address = verbs.utils.hex_to_bytes(DAI)
    dai_admin_address = verbs.utils.hex_to_bytes(DAI_ADMIN)
    morpho_blue_address = verbs.utils.hex_to_bytes(MORPHO_BLUE)
    adaptive_curve_irm_address = verbs.utils.hex_to_bytes(ADAPTIVE_CURVE_IRM)
    owner_address = verbs.utils.hex_to_bytes(OWNER)
    swap_router_address = verbs.utils.hex_to_bytes(SWAP_ROUTER)
    uniswap_weth_dai_address = verbs.utils.hex_to_bytes(UNISWAP_WETH_DAI)
    quoter_address = verbs.utils.hex_to_bytes(UNISWAP_QUOTER)

    # --------------------------------------------------
    # Morpho Blue
    # 1. Create Uniswap oracle
    # 2. Approve the LLTV
    # 3. Create a new market with ETH/DAI/LLTV/Oracle
    # 4. Supply liquidity to the market
    # -------------------------------------------------

    owner = abi.morpho_blue.owner.call(env, ZERO_ADDRESS, morpho_blue_address, [])[0][0]
    assert owner == OWNER.lower()

    # We load the Uniswap Aggregator contract that gets the price from the Uniswap pool
    with open(f"{PATH}/../abi/UniswapAggregator.json", "r") as f:
        uniswap_aggregator_contract = json.load(f)

    uniswap_aggregator_address = abi.uniswap_aggregator.constructor.deploy(
        env,
        owner_address,
        uniswap_aggregator_contract["bytecode"],
        [
            uniswap_weth_dai_address,
            weth_address,
            dai_address,
        ],
    )

    is_lltv_enabled = abi.morpho_blue.isLltvEnabled.call(
        env, verbs.utils.hex_to_bytes(owner), morpho_blue_address, [lltv]
    )[0][0]
    if not is_lltv_enabled:
        abi.morpho_blue.enableLltv.execute(
            sender=owner_address, address=morpho_blue_address, env=env, args=[lltv]
        )

    is_irm_enabled = abi.morpho_blue.isIrmEnabled.call(
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

    abi.morpho_blue.createMarket.execute(
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
        weth_abi=abi.weth_erc20,
        weth_address=weth_address,
        recipient=supplier_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(1e24),
    )

    mint_and_approve_dai(
        env=env,
        dai_abi=abi.dai,
        dai_address=dai_address,
        dai_admin_address=dai_admin_address,
        recipient=supplier_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(1e30),
    )

    # supplier supplies some DAI
    abi.morpho_blue.supply.execute(
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
    with open(f"{PATH}/../abi/MorphoBlueSnippets.json", "r") as f:
        morpho_blue_snippets_contract = json.load(f)

    morpho_blue_snippets_address = abi.morpho_blue_snippets.constructor.deploy(
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
    borrow_agent = [
        BorrowAgent(
            env=env,
            i=100 + i,
            morpho_blue_abi=abi.morpho_blue,
            morpho_blue_snippets_abi=abi.morpho_blue_snippets,
            morpho_blue_address=morpho_blue_address,
            morpho_blue_snippets_address=morpho_blue_snippets_address,
            mintable_erc20_abi=abi.weth_erc20,
            oracle_abi=abi.uniswap_aggregator,
            token_a_address=weth_address,
            token_b_address=dai_address,
            oracle_address=uniswap_aggregator_address,
            irm_address=adaptive_curve_irm_address,
            lltv=lltv,
            activation_rate=0.8,
            initial_ltv=0.75,
        )
        for i in range(n_borrow_agents)
    ]
    for i in range(n_borrow_agents):
        mint_and_approve_weth(
            env=env,
            weth_abi=abi.weth_erc20,
            weth_address=weth_address,
            contract_approved_address=morpho_blue_address,
            recipient=borrow_agent[i].address,
            amount=int(1e24),
        )

    # ----------------
    # Liquidation agent
    # ----------------
    fee = 3000

    liquidation_agent = LiquidationAgent(
        env=env,
        i=1000,
        morpho_blue_abi=abi.morpho_blue,
        mintable_erc20_abi=abi.weth_erc20,
        oracle_abi=abi.uniswap_aggregator,
        morpho_blue_snippets_abi=abi.morpho_blue_snippets,
        morpho_blue_address=morpho_blue_address,
        morpho_blue_snippets_address=morpho_blue_snippets_address,
        oracle_address=uniswap_aggregator_address,
        token_a_address=weth_address,
        token_b_address=dai_address,
        irm_address=adaptive_curve_irm_address,
        lltv=lltv,
        borrow_address=[agent.address for agent in borrow_agent],
        quoter_address=quoter_address,
        quoter_abi=abi.quoter,
        swap_router_abi=abi.swap_router,
        swap_router_address=swap_router_address,
        uniswap_fee=fee,
        uniswap_pool_abi=abi.uniswap_pool,
        uniswap_pool_address=uniswap_weth_dai_address,
        hf_threshold=0.99,
    )

    # mint and approve tokens for the liquidator agent
    # - Mint DAI and WETH
    # - Approve Morpho Blue and Swap router to use their tokens
    mint_and_approve_dai(
        env=env,
        dai_abi=abi.dai,
        dai_address=dai_address,
        contract_approved_address=morpho_blue_address,
        dai_admin_address=dai_admin_address,
        recipient=liquidation_agent.address,
        amount=int(5e29),
    )
    mint_and_approve_weth(
        env=env,
        weth_abi=abi.weth_erc20,
        weth_address=weth_address,
        recipient=liquidation_agent.address,
        contract_approved_address=morpho_blue_address,
        amount=int(5e29),
    )

    mint_and_approve_dai(
        env=env,
        dai_abi=abi.dai,
        dai_address=dai_address,
        contract_approved_address=swap_router_address,
        dai_admin_address=dai_admin_address,
        recipient=liquidation_agent.address,
        amount=int(5e29),
    )

    mint_and_approve_weth(
        env=env,
        weth_abi=abi.weth_erc20,
        weth_address=weth_address,
        recipient=liquidation_agent.address,
        contract_approved_address=swap_router_address,
        amount=int(5e29),
    )

    # ---------------
    # Uniswap agent
    # ---------------
    uniswap_agent_type = (
        partial(DummyUniswapAgent, sim_n_steps=n_steps) if init_cache else UniswapAgent
    )
    uniswap_agent = uniswap_agent_type(
        env=env,
        dt=0.01,
        fee=fee,
        i=10,
        mu=0.0,
        sigma=sigma,
        swap_router_abi=abi.swap_router,
        swap_router_address=swap_router_address,
        quoter_abi=abi.quoter,
        quoter_address=quoter_address,
        token_a_address=weth_address,
        token_b_address=dai_address,
        uniswap_pool_abi=abi.uniswap_pool,
        uniswap_pool_address=uniswap_weth_dai_address,
    )

    # mint and approve tokens for the Uniswap agent
    # - Mint DAI and WETH
    # - Approve the Swap Router to use these in their transactions
    mint_and_approve_weth(
        env=env,
        weth_abi=abi.weth_erc20,
        weth_address=weth_address,
        recipient=uniswap_agent.address,
        contract_approved_address=swap_router_address,
        amount=int(1e24),
    )
    mint_and_approve_dai(
        env=env,
        dai_abi=abi.dai,
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

    return env, results


def init_cache(
    key: str,
    block_number: int,
    seed: int,
    n_steps: int,
    n_borrow_agents: int,
    sigma: float,
    lltv: int,
):
    # Fork environment from mainnet
    env = verbs.envs.ForkEnv(
        "https://eth-mainnet.g.alchemy.com/v2/{}".format(key),
        seed,
        block_number,
    )

    env, _ = runner(
        env=env,
        seed=seed,
        n_steps=n_steps,
        n_borrow_agents=n_borrow_agents,
        sigma=sigma,
        lltv=lltv,
        init_cache=True,
    )
    cache = env.export_cache()
    with open(f"{PATH}/cache.json", "w") as f:
        json.dump(verbs.utils.cache_to_json(cache), f)

    return cache


def run_from_cache(
    seed: int, n_steps: int, n_borrow_agents: int, sigma: float, lltv: int
):

    with open(f"{PATH}/cache.json", "r") as f:
        cache_json = json.load(f)

    cache = verbs.utils.cache_from_json(cache_json)

    env = verbs.envs.EmptyEnv(seed, cache=cache)

    _, results = runner(env, seed, n_steps, n_borrow_agents, sigma, lltv)

    return results
