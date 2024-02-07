// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.10;

interface IUniswap {
    function slot0() external view returns (uint160, int24, uint16, uint16, uint16, uint8, bool);
}

interface IERC {
    function decimals() external view returns (uint8);
}

contract UniswapAggregator {
  address private _uniswap_pool_address;
  bool private _order_tokens_ab;
  // Use this to unscale the price,
  uint256 private constant divisor = uint256(2 ** 96);
  uint8 private tokenA_decimals;
  uint8 private tokenB_decimals;

  constructor(address uniswapPoolAddress, address tokenA, address tokenB) {
    // tokenA = collateral token
    // tokenB = loan token
    _uniswap_pool_address = uniswapPoolAddress;
    _order_tokens_ab = tokenA < tokenB? true : false;
    tokenA_decimals = IERC(tokenA).decimals();
    tokenB_decimals = IERC(tokenB).decimals();

  }

  function price() external view returns (int256) {
    // Uniswap returns price of token0 in terms of token1.
    // token0 and token1 are ordered in terms of their addresses
    (uint256 sqrt_price_x96,,,,,,) = IUniswap(_uniswap_pool_address).slot0();
    uint256 scaled_price = _order_tokens_ab ? 10 ** (tokenB_decimals - tokenA_decimals) * (10 ** 18 * sqrt_price_x96 / divisor) ** 2 : 10 ** (tokenA_decimals - tokenB_decimals) * (10 ** 18 * divisor / sqrt_price_x96) ** 2;
    return int256(scaled_price);
  }

}
