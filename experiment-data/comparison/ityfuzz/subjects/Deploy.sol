// SPDX-License-Identifier: MIT
pragma solidity >=0.6.0;

import "./Rubixi.sol";

contract Deploy {
    Rubixi public target;
    
    constructor() {
        target = new Rubixi();
    }
}