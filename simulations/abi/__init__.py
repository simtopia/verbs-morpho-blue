from pathlib import Path

import verbs

PATH = Path(__file__).parent

dai = verbs.abi.load_abi(f"{PATH}/dai.abi")
weth_erc20 = verbs.abi.load_abi(f"{PATH}/WETHMintableERC20.abi")

morpho_blue = verbs.abi.load_abi(f"{PATH}/MorphoBlue.abi")
uniswap_aggregator = verbs.abi.load_abi(f"{PATH}/UniswapAggregator.abi")
morpho_blue_snippets = verbs.abi.load_abi(f"{PATH}/MorphoBlueSnippets.abi")

swap_router = verbs.abi.load_abi(f"{PATH}/SwapRouter.abi")
uniswap_pool = verbs.abi.load_abi(f"{PATH}/UniswapV3Pool.abi")
quoter = verbs.abi.load_abi(f"{PATH}/Quoter_v2.abi")
