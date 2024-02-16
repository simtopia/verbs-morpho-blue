# Morpho Blue simulation with VERBS

Simulation implemented using [VERBS](https://github.com/simtopia/verbs)

## Installation & Running

This repo uses [hatch](https://hatch.pypa.io/latest/) for dependency
management. The simulation can be run using

```
hatch run examples:morpho <ALCHEMY-KEY>
```

where `<ALCHEMY-KEY>` is a API key for [Alchemy](https://www.alchemy.com/).

You can also use the `--help` argument to see additional arguments
to the scripts.

## Simulation
The script `lltv_recommender.py` runs the following simulation:
- Fork mainnet at block 19163600.
- Create a market on Morpho Blue with
    - LLTV = 0.9
    - Collateral asset: WETH
    - Borrow asset: DAI
    - Oracle: price feed is retrieved from Uniswap pool. Oracle implemented [here](./abi/UniswapAggregator.sol)
- A liquidity provider provides DAI to the above market.
- Borrowers borrow from the market.
- A trader trades in Uniswap so that the price from Uniswap follows a Geometric Brownian motion.
- A liquidator liquidates unhealthy positions.

> [!NOTE]
> The above simulation runs from a pre-generated cache of the EVM forked at block 19163600 (see the [documentation](https://simtopia.github.io/verbs/pages/verbs.envs.ForkEnv.html)). In order to generate a simulation starting from a different block, the function [`init_cache(...)`](./simulations/morpho_blue/sim.py#L320) initialises the cache at the specified block.

Simulation results are saved in `results/`.
