// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.4.16;

/**
 * Vulnerable WalletLibrary (Parity-style)
 * 仅用于安全研究/复现。请勿部署到生产或公链。
 */
contract WalletLibrary {
    mapping(address => bool) public isOwner;
    address[] public owners;
    uint public required;     // 多签门槛
    uint public daylimit;     // 与原版保持同名以便工具识别

    // === 漏洞点1：initWallet 对外可见，任何人可调用，重设 owners / required ===
    function initWallet(address[] _owners, uint _required, uint _daylimit) public {
        // 与历史问题一致：没有“只初始化一次”的保护（未使用 only_uninitialized）
        owners = _owners;
        for (uint i = 0; i < _owners.length; i++) {
            isOwner[_owners[i]] = true;
        }
        required = _required;
        daylimit = _daylimit;
    }

    // 便于 PoC：一个只有 owner 才能成功的函数（用于证明已被接管）
    function ownerOnlyAction() public view returns (bool) {
        require(isOwner[msg.sender]);
        return true;
    }

    // === 漏洞点2：kill 对外可见，任何 owner 可触发；当库本体被“初始化接管”后即可自毁 ===
    function kill(address _to) external {
        require(isOwner[msg.sender]);
        selfdestruct(_to); // 自毁库本体 => 所有依赖它的代理钱包将失效
    }
}
