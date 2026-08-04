/**
 * Harness contract to expose an invariant for Rubixi access control.
 * Goal: detect that anyone can reclaim/change ownership by calling `DynamicPyramid()` multiple times.
 * Method: once creator becomes non-zero, it must never change. If it changes, invariant fails.
 *
 * ityfuzz will look for functions prefixed with `invariant_` (enabled via `--invariant-oracle`)
 * and treat a revert / failure flag as violation. We implement as boolean returning function
 * that returns false once the owner changes after first set.
 */
pragma solidity ^0.4.11; // align with old compiler semantics (constructor confusion vulnerability)

import "./Rubixi.sol";

contract RubixiInvariant {
    Rubixi public target;
    address private firstOwner; // snapshot after first non-zero set
    bool private locked;        // whether snapshot taken

    constructor(Rubixi _target) public {
        target = _target;
    }

    // Invariant: once owner (creator) is non-zero, it must not change.
    // Returns true if invariant currently holds, false if violated.
    function invariant_owner_constant() public returns (bool) {
        address current = target.creatorAddress();
        if (!locked) {
            if (current == address(0)) {
                return true; // 未初始化，不锁定
            }
            firstOwner = current;
            locked = true;
            return true;
        }
        // 不变量：一旦锁定，owner 不得变化。变化则 revert 触发 invariant oracle。
        require(current == firstOwner, "owner changed");
        return true;
    }
}
