// SPDX-License-Identifier: MIT
pragma solidity ^0.4.26;

interface IERC20Lite {
    function balanceOf(address a) external view returns (uint256);
}

/// @notice Vulnerable Governance: counts voting power as current balanceOf at vote time.
/// No snapshots, no locking, no delay -> flash-loan governance attack possible.
contract VulnerableGovernance {
    struct Proposal {
        address proposer;
        address target;
        uint256 value;
        bytes   data;
        uint256 yesVotes;
        uint256 noVotes;
        uint64  startBlock;
        uint64  endBlock;
        bool    executed;
    }

    IERC20Lite public govToken;
    uint256 public quorum;      // minimal yesVotes required
    uint256 public majorityBP;  // e.g., 5000 = 50%
    uint64  public votingPeriod; // in blocks

    Proposal[] public proposals;
    mapping(uint256 => mapping(address=>bool)) public hasVoted;

    event Proposed(uint256 id, address proposer, address target, uint256 value);
    event Voted(uint256 id, address voter, bool support, uint256 weight);
    event Executed(uint256 id, bool ok);

    constructor(IERC20Lite _govToken, uint256 _quorum, uint256 _majorityBP, uint64 _votingPeriod) public {
        govToken = _govToken;
        quorum = _quorum;
        majorityBP = _majorityBP;
        votingPeriod = _votingPeriod; // keep small in PoC; can even be 0
    }

    function propose(address target, uint256 value, bytes data) public returns (uint256 id) {
        id = proposals.length;
        proposals.push(Proposal({
            proposer: msg.sender,
            target: target,
            value: value,
            data: data,
            yesVotes: 0,
            noVotes: 0,
            startBlock: uint64(block.number),
            endBlock: uint64(block.number + uint256(votingPeriod)),
            executed: false
        }));
        emit Proposed(id, msg.sender, target, value);
    }

    /// @dev VULNERABLE: reads current balanceOf(msg.sender) as weight (flash-loanable).
    function vote(uint256 id, bool support) external {
        Proposal storage p = proposals[id];
        require(block.number <= p.endBlock, "ended");
        require(!hasVoted[id][msg.sender], "voted");
        uint256 weight = govToken.balanceOf(msg.sender); // <-- VULNERABLE POINT
        require(weight > 0, "no power");
        hasVoted[id][msg.sender] = true;
        if (support) p.yesVotes += weight; else p.noVotes += weight;
        emit Voted(id, msg.sender, support, weight);
    }

    /// @dev VULNERABLE: no delay / no snapshot re-check, can be executed immediately.
    function execute(uint256 id) external {
        Proposal storage p = proposals[id];
        require(!p.executed, "done");
        require(block.number > p.endBlock, "not ended");

        uint256 total = p.yesVotes + p.noVotes;
        require(p.yesVotes >= quorum, "no quorum");
        // majority basis points check
        require(p.yesVotes * 10000 >= majorityBP * total, "not majority");

        p.executed = true;
        (bool ok,) = p.target.call.value(p.value)(p.data);
        emit Executed(id, ok);
    }

    // helper views
    function proposalsCount() external view returns (uint256) { return proposals.length; }
}
