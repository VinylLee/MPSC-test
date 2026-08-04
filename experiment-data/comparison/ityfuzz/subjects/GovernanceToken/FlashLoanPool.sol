// SPDX-License-Identifier: MIT
pragma solidity ^0.4.26;

interface IERC20 {
    function transfer(address to, uint256 v) external returns (bool);
    function transferFrom(address f, address to, uint256 v) external returns (bool);
    function balanceOf(address a) external view returns (uint256);
    function approve(address s, uint256 v) external returns (bool);
}

interface IFlashBorrower {
    function onFlashLoan(address token, uint256 amount, bytes data) external;
}

/// @notice Very simple flash loan pool for GOV token. No fees, single-tx payback.
contract FlashLoanPool {
    IERC20 public token;

    constructor(IERC20 _token) public {
        token = _token;
    }

    /// @notice Borrow `amount` and call borrower, expecting it to return tokens before end.
    function flashLoan(uint256 amount, bytes data) external {
        uint256 balBefore = token.balanceOf(address(this));
        require(balBefore >= amount, "insufficient-liquidity");

        // send to borrower
        require(token.transfer(msg.sender, amount), "transfer-out");
        IFlashBorrower(msg.sender).onFlashLoan(address(token), amount, data);

        // require full payback in same tx
        uint256 balAfter = token.balanceOf(address(this));
        require(balAfter >= balBefore, "not-repaid");
    }
}
