pragma solidity ^0.4.11;

contract MyToken {
    mapping (address => uint) balances;
    event Transfer(address indexed _from, address indexed _to, uint256 _value);

    // ❌ 漏洞1: 使用 tx.origin 初始化余额（可能被钓鱼合约利用）
    function MyToken() public {
        balances[tx.origin] = 10000;
    }

    // ❌ 漏洞2: 使用 uint16 可能溢出（最大 65535），但 balances 是 uint，类型不一致
    // ❌ 漏洞3: 没有检查地址有效性 (to 可能是 address(0))
    // ❌ 漏洞4: 没有使用 SafeMath，存在整数溢出/下溢风险
    function sendCoin(address to, uint16 amount) public returns(bool sufficient) {
        if (balances[msg.sender] < amount) return false;
        balances[msg.sender] -= amount;
        balances[to] += amount;
        Transfer(msg.sender, to, amount); // ❌ 老语法，建议用 emit
        return true;
    }

    // ❌ 漏洞5: 使用 constant 而不是 view
    function getBalance(address addr) public constant returns(uint) {
        return balances[addr];
    }
}
