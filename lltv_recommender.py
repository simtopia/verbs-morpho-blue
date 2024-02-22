import argparse
import json
import os
from itertools import product

import verbs
from verbs.batch_runner import batch_run

import simulations

if __name__ == "__main__":

    parser = argparse.ArgumentParser(prog="Morpho Blue agent-based simulation")

    parser.add_argument("--seed", type=int, default=101, help="Random seed")
    parser.add_argument(
        "--n_borrow_agents", type=int, default=10, help="Number of borrowing agents"
    )
    parser.add_argument("--sigma", type=float, default=0.3, help="price volatility")

    parser.add_argument(
        "--n_steps", type=int, default=100, help="Number of steps of the simulation"
    )
    parser.add_argument(
        "--batch_runner",
        action="store_true",
        help="Run batch of simulations over different simulation parameters",
    )

    args = parser.parse_args()

    assert (
        0 < args.n_borrow_agents < 100
    ), "Number of borrow agents must be between 0 and 100"

    if args.batch_runner:
        # run a batch of simulations
        lltv = 9 * 10**17
        parameters_samples = [
            dict(mu=mu, sigma=sigma)
            for mu, sigma in product([0.0, 0.1, -0.1], [0.1, 0.2, 0.3])
        ]

        with open(os.path.join("simulations", "morpho_blue", "cache.json"), "r") as f:
            cache_json = json.load(f)
        cache = verbs.utils.cache_from_json(cache_json)

        batch_results = batch_run(
            simulations.morpho_blue.sim.run_from_batch_runner,
            n_steps=args.n_steps,
            n_samples=10,
            parameters_samples=parameters_samples,
            cache=cache,
            n_borrow_agents=args.n_borrow_agents,
            lltv=lltv,
        )
        simulations.utils.postprocessing.save(batch_results, path="results/morpho_blue")

    else:
        lltv = 9 * 10**17
        results = simulations.morpho_blue.sim.run_from_cache(
            seed=args.seed,
            n_steps=args.n_steps,
            n_borrow_agents=args.n_borrow_agents,
            sigma=args.sigma,
            lltv=lltv,
        )

        simulations.morpho_blue.plotting.plot_results_borrowers(
            records=results, lltv=lltv / 10**18, n_borrow_agents=args.n_borrow_agents
        )
