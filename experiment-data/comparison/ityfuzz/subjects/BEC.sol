pragma solidity ^0.4.16;  // 更接近历史环境

contract BeautyEcosystemCoin {
    string public name = "Beauty Ecosystem Coin";
    string public symbol = "BEC";
    uint8 public decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;

    event Transfer(address indexed from, address indexed to, uint256 value);

    function BeautyEcosystemCoin(uint256 _initialSupply) public {
        totalSupply = _initialSupply * 10 ** uint256(decimals);
        balanceOf[msg.sender] = totalSupply;
    }

    function transfer(address _to, uint256 _value) public returns (bool success) {
        require(balanceOf[msg.sender] >= _value);
        balanceOf[msg.sender] -= _value;
        balanceOf[_to] += _value;
        Transfer(msg.sender, _to, _value); // <-- 没有 emit
        return true;
    }

    function batchTransfer(address[] _receivers, uint256 _value) public returns (bool success) {
        uint cnt = _receivers.length;
        uint amount = cnt * _value; // 漏洞点
        require(balanceOf[msg.sender] >= amount);

        balanceOf[msg.sender] -= amount;
        for (uint i = 0; i < cnt; i++) {
            balanceOf[_receivers[i]] += _value;
            Transfer(msg.sender, _receivers[i], _value); // <-- 没有 emit
        }
        return true;
    }
}
