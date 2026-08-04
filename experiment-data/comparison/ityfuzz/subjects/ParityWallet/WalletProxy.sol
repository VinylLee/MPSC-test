// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.4.16;

contract WalletProxy {
    address public libraryAddress; // 指向 WalletLibrary

    function WalletProxy(address _lib) public {
        libraryAddress = _lib;
    }

  // 单一 fallback：既能收 ETH，又能转发
    function() public payable {
        address _impl = libraryAddress;
        require(_impl != address(0));
        assembly {
            calldatacopy(0x0, 0x0, calldatasize)
            let r := delegatecall(gas, _impl, 0x0, calldatasize, 0, 0)
            let size := returndatasize
            returndatacopy(0x0, 0x0, size)
            switch r
            case 0 { revert(0x0, size) }
            default { return (0x0, size) }
        }
    }
}
