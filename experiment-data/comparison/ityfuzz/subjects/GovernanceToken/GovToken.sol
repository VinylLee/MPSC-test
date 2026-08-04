// SPDX-License-Identifier: MIT
pragma solidity ^0.4.26;

/// @notice Minimal ERC20 for testing
contract GovToken {
    string public name = "Governance Token";
    string public symbol = "GOV";
    uint8  public decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address=>uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 v);
    event Approval(address indexed o, address indexed s, uint256 v);

    constructor(uint256 initialSupply) public {
        _mint(msg.sender, initialSupply);
    }

    function _mint(address to, uint256 v) internal {
        totalSupply = totalSupply + v;
        balanceOf[to] = balanceOf[to] + v;
        emit Transfer(address(0), to, v);
    }

    function transfer(address to, uint256 v) external returns (bool) {
        require(balanceOf[msg.sender] >= v, "bal");
        balanceOf[msg.sender] = balanceOf[msg.sender] - v;
        balanceOf[to] = balanceOf[to] + v;
        emit Transfer(msg.sender, to, v);
        return true;
    }

    function approve(address s, uint256 v) external returns (bool) {
        allowance[msg.sender][s] = v;
        emit Approval(msg.sender, s, v);
        return true;
    }

    function transferFrom(address f, address to, uint256 v) external returns (bool) {
        require(balanceOf[f] >= v, "bal");
        require(allowance[f][msg.sender] >= v, "allow");
        balanceOf[f] = balanceOf[f] - v;
        allowance[f][msg.sender] = allowance[f][msg.sender] - v;
        balanceOf[to] = balanceOf[to] + v;
        emit Transfer(f, to, v);
        return true;
    }
}
